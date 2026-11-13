(() => {
  const page = document.body.dataset.page;
  const api = async (path, options = {}) => {
    const response = await fetch(path, { credentials: "same-origin", ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
    const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  };
  const money = (value) => new Intl.NumberFormat("ru-RU").format(value) + " ₽";
  const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
  const setMessage = (id, text, bad = false) => { const el = document.getElementById(id); if (el) { el.textContent = text; el.style.color = bad ? "#a4594b" : ""; } };

  async function initShell() {
    const host = document.getElementById("app-shell");
    if (!host) return;
    const session = await api("/api/session");
    if (!session.authenticated) { location.replace("/login"); return; }
    const links = [["catalog","Каталог","/catalog"],["cart","Корзина","/cart"],["profile","Профиль","/profile"],["settings","Настройки","/settings"]];
    host.innerHTML = `<header class="app-header"><a class="brand" href="/catalog"><span class="brand-mark">DQ</span><span>DevTools QA Lab</span></a><nav class="nav">${links.map(([id,label,url])=>`<a class="${page===id?"active":""}" href="${url}">${label}${id==="cart"?` <span id="cart-count"></span>`:""}</a>`).join("")}</nav><div class="header-actions"><span class="user-chip">Анна Морозова</span><button id="reset-button" class="button reset" type="button">Сбросить стенд</button><button id="logout-button" class="button secondary small" type="button">Выйти</button></div></header>`;
    document.getElementById("logout-button").addEventListener("click", async () => { try { await api("/api/logout", {method:"POST", body:"{}"}); } finally { location.href="/login"; } });
    document.getElementById("reset-button").addEventListener("click", async () => { if (!confirm("Вернуть данные стенда к исходным?")) return; await api("/api/reset", {method:"POST", body:"{}"}); localStorage.clear(); location.href="/login"; });
    localStorage.setItem("qa_last_section", page);
    updateCartCount();
  }

  async function updateCartCount() {
    const count = document.getElementById("cart-count");
    if (!count) return;
    try { const cart = await api("/api/cart"); count.textContent = cart.units ? `(${cart.units})` : ""; } catch (_) { count.textContent = ""; }
  }

  function loginPage() {
    const form = document.getElementById("login-form");
    const performLogin = async () => {
      setMessage("login-message", "Проверяем данные…");
      try {
        const result = await api("/api/login", {method:"POST", body:JSON.stringify({username:form.username.value, password:form.password.value})});
        localStorage.setItem("qa_user", result.user);
        location.href = "/catalog";
      } catch (error) { setMessage("login-message", error.message, true); }
    };
    form.addEventListener("submit", (event) => { event.preventDefault(); performLogin(); });
    document.getElementById("login-button").addEventListener("click", performLogin);
  }

  async function loadCatalog() {
    const host = document.getElementById("catalog-list");
    const {items} = await api("/api/catalog");
    const icons = {101:"☕",102:"▤",103:"◉"};
    host.innerHTML = items.map(item => `<article class="product-card"><div class="product-art ${item.tone}">${icons[item.id]||"◇"}</div><p class="product-category">${esc(item.category)}</p><h2>${esc(item.name)}</h2><p class="product-description">${esc(item.description)}</p><div class="product-bottom"><span class="price">${money(item.price)}</span><button class="button primary add-button" data-id="${item.id}">Добавить 1 шт.</button></div></article>`).join("");
    host.querySelectorAll(".add-button").forEach(button => button.addEventListener("click", async () => {
      try { await api("/api/cart/items", {method:"POST", body:JSON.stringify({productId:Number(button.dataset.id), quantity:2})}); showToast("Товар добавлен в корзину"); updateCartCount(); }
      catch(error) { showToast(error.message); }
    }));
  }

  function showToast(text) { const el=document.getElementById("catalog-message"); if(!el) return; el.textContent=text; el.classList.add("visible"); setTimeout(()=>el.classList.remove("visible"),2200); }

  async function loadCart() {
    const host = document.getElementById("cart-content");
    const cart = await api("/api/cart");
    if (!cart.items.length) { host.innerHTML = `<div class="empty-state"><p>Корзина пока пуста.</p><a class="button primary" href="/catalog">Перейти в каталог</a></div>`; return; }
    host.innerHTML = `<div>${cart.items.map(line=>`<div class="cart-row"><div><div class="cart-name">${esc(line.product.name)}</div><div class="cart-meta">${money(line.product.price)} за единицу</div></div><div class="quantity-pill">${line.quantity} шт.</div><div class="cart-total">${money(line.lineTotal)}</div><button class="remove-button" data-id="${line.product.id}">Удалить</button></div>`).join("")}</div><div class="cart-summary"><span>Итого</span><strong>${money(cart.total)}</strong></div>`;
    host.querySelectorAll(".remove-button").forEach(button => button.addEventListener("click", async () => { await api(`/api/cart/items/${button.dataset.id}`, {method:"DELETE"}); await loadCart(); updateCartCount(); }));
  }

  async function loadProfile() {
    const {profile}=await api("/api/profile");
    const form=document.getElementById("profile-form");
    const fill=(data)=>{form.elements.name.value=data.name;form.elements.email.value=data.email;form.elements.phone.value=data.phone;};
    fill(profile);
    form.addEventListener("submit", async (event)=>{event.preventDefault();setMessage("profile-message","Сохраняем…");const payload={name:form.elements.name.value,email:form.elements.email.value,phone:form.elements.phone.value};try{const result=await api("/api/profile",{method:"PUT",body:JSON.stringify(payload)});fill(result.profile);setMessage("profile-message","Профиль сохранён");}catch(error){setMessage("profile-message",error.message,true);}});
  }

  let allFeed=[];
  async function loadFeed() {
    const {version,entries}=await api("/api/settings/feed");
    document.getElementById("feed-version").textContent=version;
    allFeed=entries;
    renderFeed();
  }
  function renderFeed() {
    const selected=document.getElementById("category-filter").value;
    const entries=selected==="Все"?allFeed:allFeed.filter(x=>x.category===selected);
    const host=document.getElementById("feed-list");
    host.innerHTML=entries.length?entries.map(x=>`<div class="feed-row"><div><div class="feed-title">${esc(x.title)}</div><div class="feed-meta">${esc(x.id)} · ${esc(x.category)}</div></div><span class="status ${x.status==="На проверке"?"review":""}">${esc(x.status)}</span></div>`).join(""):`<div class="empty-state">Для этой категории пока нет записей.</div>`;
  }
  function settingsPage() {
    document.getElementById("filter-button").addEventListener("click",renderFeed);
    document.getElementById("refresh-button").addEventListener("click",async()=>{setMessage("feed-message","Загружаем данные…");try{await loadFeed();setMessage("feed-message","Данные обновлены");}catch(e){setMessage("feed-message",e.message,true);}});
    document.getElementById("publish-button").addEventListener("click",async()=>{try{const result=await api("/api/settings/publish",{method:"POST",body:"{}"});setMessage("feed-message",`Опубликована версия ${result.version}`);}catch(e){setMessage("feed-message",e.message,true);}});
    document.getElementById("summary-button").addEventListener("click",showSummary);
    loadFeed();
  }
  function showSummary() {
    debugger;
    document.getElementById("summary-output").textContent = `Всего записей: ${summaryState.total}`;
  }

  async function start() {
    if (page === "login") return loginPage();
    await initShell();
    if (!document.getElementById("app-shell")?.innerHTML) return;
    if (page === "catalog") await loadCatalog();
    if (page === "cart") await loadCart();
    if (page === "profile") await loadProfile();
    if (page === "settings") settingsPage();
  }
  start().catch(error => { console.error("DevTools QA Lab:", error); });
})();
