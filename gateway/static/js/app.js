/* =========================================================
   Tropicana Guide — frontend logic
   Talks to our own Flask backend (/api/pois, /api/assistant)
   rather than any external service directly, except:
     - OpenStreetMap tiles (map imagery)
     - OSRM (free public routing engine, no key needed)
   ========================================================= */
const CENTER = { lat: 3.8225, lng: 11.5235 };

const CATEGORIES = {
  hotel:      { label: "Hotels",              color: "#B33F2A", icon: "🏨" },
  restaurant: { label: "Restaurants",         color: "#E3A93B", icon: "🍽️" },
  hospital:   { label: "Hospitals & Clinics", color: "#C0392B", icon: "⛑️" },
  pharmacy:   { label: "Pharmacies",          color: "#0B7285", icon: "➕" },
  school:     { label: "Schools",             color: "#163A2E", icon: "🎓" },
  market:     { label: "Markets",              color: "#6B4226", icon: "🧺" },
  fuel:       { label: "Fuel Stations",        color: "#2D6A4F", icon: "⛽" },
  bank:       { label: "Banks",                color: "#5C4D7D", icon: "🏦" },
  office:     { label: "Offices & Organisations", color: "#8A6D3B", icon: "🏢" }
};

let ALL_POIS = [];
let markers = {};
let routeLayer = null;
let activePoi = null;
let activeCategories = new Set();

/* ---------- Map setup ---------- */
const map = L.map('map', { zoomControl:false }).setView([CENTER.lat, CENTER.lng], 14);
L.control.zoom({ position:'bottomleft' }).addTo(map);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 19
}).addTo(map);

L.marker([CENTER.lat, CENTER.lng], {
  icon: L.divIcon({
    className:'',
    html:`<div style="width:16px;height:16px;border-radius:50%;background:#E3A93B;border:3px solid #163A2E;box-shadow:0 0 0 6px rgba(227,169,59,0.35);"></div>`,
    iconSize:[16,16], iconAnchor:[8,8]
  })
}).addTo(map).bindPopup("<b>Tropicana</b><br>Reference point for this guide");

/* ---------- Collapse place labels when zoomed out, to avoid clutter ---------- */
const LABEL_MIN_ZOOM = 14;
function updateLabelVisibility(){
  const el = map.getContainer();
  if(map.getZoom() < LABEL_MIN_ZOOM){ el.classList.add('hide-poi-labels'); }
  else { el.classList.remove('hide-poi-labels'); }
}
map.on('zoomend', updateLabelVisibility);
updateLabelVisibility();

function makeIcon(cat){
  const meta = CATEGORIES[cat] || { color:"#333", icon:"📍" };
  return L.divIcon({
    className:'',
    html:`<div class="poi-marker" style="background:${meta.color}"><span>${meta.icon}</span></div>`,
    iconSize:[26,26], iconAnchor:[13,26]
  });
}

/* ---------- Load real data from our own backend ---------- */
async function loadPois(){
  const res = await fetch('/api/pois');
  ALL_POIS = await res.json();

  ALL_POIS.forEach(p => {
    const m = L.marker([p.lat, p.lng], { icon: makeIcon(p.category) }).addTo(map);
    m.bindTooltip(p.name, {
      permanent: true,
      direction: 'top',
      offset: [0, -22],
      className: 'poi-label'
    });
    if(p.image){
      m.on('mouseover', () => {
        L.popup({ closeButton: false, className: 'poi-hover-popup', offset: [0, -8] })
          .setLatLng([p.lat, p.lng])
          .setContent(`<img src="${p.image}" alt="${p.name}"><div class="poi-hover-name">${p.name}</div>`)
          .openOn(map);
      });
      m.on('mouseout', () => { map.closePopup(); });
    }
    m.on('click', () => selectPoi(p.id));
    markers[p.id] = m;
  });

  buildChips();
  renderList();
}

/* ---------- Sidebar: chips ---------- */
function buildChips(){
  const chipRow = document.getElementById('chipRow');
  chipRow.innerHTML = '';
  Object.entries(CATEGORIES).forEach(([key, meta]) => {
    const chip = document.createElement('div');
    chip.className = 'chip';
    chip.innerHTML = `<span class="dot" style="background:${meta.color}"></span>${meta.icon} ${meta.label}`;
    chip.addEventListener('click', () => {
      if(activeCategories.has(key)){ activeCategories.delete(key); chip.classList.remove('active'); }
      else { activeCategories.add(key); chip.classList.add('active'); }
      renderList();
    });
    chipRow.appendChild(chip);
  });
}

const searchInput = document.getElementById('searchInput');
searchInput.addEventListener('input', renderList);

function filteredPois(){
  const q = searchInput.value.trim().toLowerCase();
  return ALL_POIS.filter(p => {
    const matchesCat = activeCategories.size === 0 || activeCategories.has(p.category);
    const matchesText = !q || p.name.toLowerCase().includes(q) || p.address.toLowerCase().includes(q) || p.category.toLowerCase().includes(q);
    return matchesCat && matchesText;
  });
}

function poiIconHtml(p, meta){
  if(p.image){
    return `<img src="${p.image}" alt="${p.name}">`;
  }
  return meta.icon;
}

function renderList(){
  const list = document.getElementById('poiList');
  const items = filteredPois();
  list.innerHTML = '';
  if(items.length === 0){
    list.innerHTML = `<div class="empty-state">No places match that search.<br>Try a different name or category.</div>`;
    return;
  }
  items.forEach(p => {
    const meta = CATEGORIES[p.category] || { label:p.category, color:"#333", icon:"📍" };
    const card = document.createElement('div');
    card.className = 'poi-card' + (activePoi === p.id ? ' selected' : '');
    card.innerHTML = `
      <div class="poi-top">
        <div class="poi-icon" style="background:${meta.color}">${poiIconHtml(p, meta)}</div>
        <div>
          <div class="poi-name">${p.name}</div>
          <div class="poi-meta">${meta.label} · ${p.address}</div>
          ${p.rating ? `<div class="poi-rating">★ ${Number(p.rating).toFixed(1)}</div>` : ''}
        </div>
      </div>`;
    card.addEventListener('click', () => selectPoi(p.id));
    list.appendChild(card);
  });
}

/* ---------- Detail panel + routing ---------- */
const detailPanel = document.getElementById('detailPanel');
document.getElementById('detailClose').addEventListener('click', () => {
  detailPanel.classList.remove('show');
  activePoi = null;
  renderList();
});

function selectPoi(id){
  const p = ALL_POIS.find(x => x.id === id);
  if(!p) return;
  activePoi = id;
  renderList();
  map.flyTo([p.lat, p.lng], 16, { duration: 0.6 });
  markers[id].openPopup();

  const meta = CATEGORIES[p.category] || { label:p.category, color:"#333" };
  document.getElementById('detailCatLabel').textContent = meta.label;
  document.getElementById('detailCatLabel').style.background = meta.color;
  document.getElementById('detailName').textContent = p.name;
  document.getElementById('detailAddress').textContent = "📍 " + p.address + (p.note ? " — " + p.note : "");
  document.getElementById('detailPhone').textContent = p.phone ? "📞 " + p.phone : "";
  document.getElementById('detailRating').textContent = p.rating ? "★ " + Number(p.rating).toFixed(1) + " rating" : "";
  const photoEl = document.getElementById('detailPhoto');
  const badgeEl = document.getElementById('detailPhotoBadge');
  if(p.image){
    photoEl.src = p.image;
    photoEl.alt = p.name;
    photoEl.style.display = 'block';
    badgeEl.style.display = p.image_placeholder ? 'block' : 'none';
  } else {
    photoEl.style.display = 'none';
    badgeEl.style.display = 'none';
  }

  const callBtn = document.getElementById('btnCall');
  if(p.phone){ callBtn.style.display='inline-flex'; callBtn.href = 'tel:' + p.phone.replace(/\s/g,''); }
  else { callBtn.style.display='none'; }

  document.getElementById('routeInfo').classList.remove('show');
  detailPanel.classList.add('show');

  if(routeLayer){ map.removeLayer(routeLayer); routeLayer = null; }
}

document.getElementById('btnDirections').addEventListener('click', () => {
  const p = ALL_POIS.find(x => x.id === activePoi);
  if(!p) return;
  const routeInfo = document.getElementById('routeInfo');
  routeInfo.textContent = "Finding your route…";
  routeInfo.classList.add('show');

  const startFrom = (start) => fetchRoute(start, p, routeInfo);

  if(navigator.geolocation){
    navigator.geolocation.getCurrentPosition(
      pos => startFrom({ lat: pos.coords.latitude, lng: pos.coords.longitude, label:"your current location" }),
      () => startFrom({ lat: CENTER.lat, lng: CENTER.lng, label:"the Tropicana roundabout" }),
      { timeout: 4000 }
    );
  } else {
    startFrom({ lat: CENTER.lat, lng: CENTER.lng, label:"the Tropicana roundabout" });
  }
});

function fetchRoute(start, dest, routeInfo){
  const url = `https://router.project-osrm.org/route/v1/driving/${start.lng},${start.lat};${dest.lng},${dest.lat}?overview=full&geometries=geojson`;
  fetch(url)
    .then(r => r.json())
    .then(data => {
      if(!data.routes || !data.routes.length){ throw new Error('no route'); }
      const route = data.routes[0];
      if(routeLayer) map.removeLayer(routeLayer);
      routeLayer = L.geoJSON(route.geometry, { style:{ color:'#B33F2A', weight:5, opacity:0.85 } }).addTo(map);
      map.fitBounds(routeLayer.getBounds(), { padding:[60,60] });
      const km = (route.distance/1000).toFixed(1);
      const mins = Math.round(route.duration/60);
      routeInfo.textContent = `🚗 ${km} km · about ${mins} min driving from ${start.label}`;
    })
    .catch(() => {
      routeInfo.textContent = "Couldn't calculate a live route right now — try again in a moment.";
    });
}

/* ---------- Sidebar toggle (mobile) ---------- */
document.getElementById('sidebarToggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('collapsed');
});

/* ---------- AI assistant (calls OUR backend, not Anthropic directly) ---------- */
const assistantFab = document.getElementById('assistantFab');
const assistantPanel = document.getElementById('assistantPanel');
const assistantMessages = document.getElementById('assistantMessages');
const assistantInput = document.getElementById('assistantInput');

assistantFab.addEventListener('click', () => {
  assistantPanel.classList.toggle('show');
});
document.getElementById('assistantClose').addEventListener('click', () => assistantPanel.classList.remove('show'));

let chatHistory = [];

function addMessage(text, role, sourceTag){
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  if(sourceTag){
    const tag = document.createElement('span');
    tag.className = 'src-tag';
    tag.textContent = sourceTag === 'live' ? '⚡ live AI answer' : '🧭 local guide answer';
    div.appendChild(tag);
  }
  assistantMessages.appendChild(div);
  assistantMessages.scrollTop = assistantMessages.scrollHeight;
}

function handleAssistantAction(action){
  if(!action) return;

  if(action.type === 'focus'){
    map.flyTo([action.lat, action.lng], 16, { duration: 0.6 });
    L.popup().setLatLng([action.lat, action.lng]).setContent(`<b>${action.label}</b>`).openOn(map);
    return;
  }

  if(action.type === 'directions'){
    const { from, to } = action;
    if(routeLayer){ map.removeLayer(routeLayer); routeLayer = null; }

    document.getElementById('detailCatLabel').textContent = "Directions";
    document.getElementById('detailCatLabel').style.background = "#B33F2A";
    document.getElementById('detailName').textContent = to.label;
    document.getElementById('detailAddress').textContent = `From ${from.label} to ${to.label}`;
    document.getElementById('detailPhone').textContent = '';
    document.getElementById('detailRating').textContent = '';
    document.getElementById('btnCall').style.display = 'none';
    document.getElementById('detailPhoto').style.display = 'none';
    document.getElementById('detailPhotoBadge').style.display = 'none';
    detailPanel.classList.add('show');

    const routeInfo = document.getElementById('routeInfo');
    routeInfo.textContent = "Drawing your route…";
    routeInfo.classList.add('show');

    fetchRoute(
      { lat: from.lat, lng: from.lng, label: from.label },
      { lat: to.lat, lng: to.lng },
      routeInfo
    );
    map.flyTo([to.lat, to.lng], 15, { duration: 0.6 });
  }
}

async function sendAssistantMessage(){
  const text = assistantInput.value.trim();
  if(!text) return;
  addMessage(text, 'user');
  assistantInput.value = '';

  const typing = document.createElement('div');
  typing.className = 'typing';
  typing.textContent = 'Your guide is thinking…';
  assistantMessages.appendChild(typing);
  assistantMessages.scrollTop = assistantMessages.scrollHeight;

  try{
    const headers = { 'Content-Type': 'application/json' };
    if(authToken) headers['Authorization'] = 'Bearer ' + authToken;
    const response = await fetch('/api/assistant', {
      method: 'POST',
      headers,
      body: JSON.stringify({ message: text, history: chatHistory, conversation_id: currentConversationId })
    });
    const data = await response.json();
    typing.remove();

    addMessage(data.reply, 'bot', data.source);
    chatHistory.push({ role:'user', content: text });
    chatHistory.push({ role:'assistant', content: data.reply });
    if(data.conversation_id) currentConversationId = data.conversation_id;
    handleAssistantAction(data.action);
  } catch(err){
    typing.remove();
    addMessage("I couldn't reach the guide service right now — please check that the app server is running.", 'system-note');
  }
}

document.getElementById('assistantSend').addEventListener('click', sendAssistantMessage);
assistantInput.addEventListener('keydown', e => { if(e.key === 'Enter') sendAssistantMessage(); });

/* ---------- Boot ---------- */
loadPois();

/* ---------- Auth ---------- */
let authToken = localStorage.getItem('tg_token') || null;
let currentUsername = localStorage.getItem('tg_username') || null;
let historyLoaded = false;

const accountBtn = document.getElementById('accountBtn');
const authModalOverlay = document.getElementById('authModalOverlay');
const authModalClose = document.getElementById('authModalClose');
const tabLogin = document.getElementById('tabLogin');
const tabRegister = document.getElementById('tabRegister');
const authForm = document.getElementById('authForm');
const authError = document.getElementById('authError');
const authSubmit = document.getElementById('authSubmit');
let authMode = 'login';

function updateAccountUI(){
  accountBtn.textContent = currentUsername ? `👤 ${currentUsername} (sign out)` : '👤 Sign in';
  const historyBtn = document.getElementById('assistantHistoryBtn');
  if(historyBtn) historyBtn.style.display = currentUsername ? 'inline-flex' : 'none';
}
updateAccountUI();

accountBtn.addEventListener('click', () => {
  if(currentUsername){
    authToken = null; currentUsername = null; historyLoaded = false;
    currentConversationId = null; viewingHistory = false;
    localStorage.removeItem('tg_token'); localStorage.removeItem('tg_username');
    updateAccountUI();
    showChatView();
    assistantMessages.innerHTML = '';
    addMessage("Mbolo! 👋 I'm Wura, your local guide for the Tropicana area. Ask me things like \"where can I get fuel near here\" or \"any good restaurants close by\" and I'll point you to real places on this map.", 'bot');
    chatHistory = [];
    return;
  }
  authMode = 'login';
  tabLogin.classList.add('active'); tabRegister.classList.remove('active');
  authSubmit.textContent = 'Sign in';
  authError.textContent = '';
  authModalOverlay.classList.add('show');
});

authModalClose.addEventListener('click', () => authModalOverlay.classList.remove('show'));

tabLogin.addEventListener('click', () => {
  authMode = 'login';
  tabLogin.classList.add('active'); tabRegister.classList.remove('active');
  authSubmit.textContent = 'Sign in';
  authError.textContent = '';
});
tabRegister.addEventListener('click', () => {
  authMode = 'register';
  tabRegister.classList.add('active'); tabLogin.classList.remove('active');
  authSubmit.textContent = 'Create account';
  authError.textContent = '';
});

authForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = document.getElementById('authUsername').value.trim();
  const password = document.getElementById('authPassword').value;
  const endpoint = authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if(!res.ok){
      authError.textContent = data.error || 'Something went wrong.';
      return;
    }
    authToken = data.token;
    currentUsername = data.username;
    localStorage.setItem('tg_token', authToken);
    localStorage.setItem('tg_username', currentUsername);
    authModalOverlay.classList.remove('show');
    updateAccountUI();
    currentConversationId = null;
  } catch(err){
    authError.textContent = "Couldn't reach the server — please try again.";
  }
});

async function verifyStoredAuth(){
  if(!authToken) return;
  try {
    const res = await fetch('/api/auth/me', { headers: { 'Authorization': 'Bearer ' + authToken } });
    if(!res.ok){
      authToken = null; currentUsername = null;
      localStorage.removeItem('tg_token'); localStorage.removeItem('tg_username');
    }
    updateAccountUI();
  } catch(err){ /* ignore — assume still valid, will fail gracefully later if not */ }
}
verifyStoredAuth();

/* ---------- Conversations (Wura chat history, grouped by topic) ---------- */
let currentConversationId = null;
let viewingHistory = false;

function showConversationList(){
  assistantMessages.style.display = 'none';
  document.getElementById('assistantInputRow').style.display = 'none';
  document.getElementById('assistantConversations').style.display = 'flex';
}
function showChatView(){
  document.getElementById('assistantConversations').style.display = 'none';
  assistantMessages.style.display = 'flex';
  document.getElementById('assistantInputRow').style.display = 'flex';
}

async function loadConversationList(){
  const list = document.getElementById('conversationList');
  list.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const res = await fetch('/api/assistant/conversations', {
      headers: { 'Authorization': 'Bearer ' + authToken }
    });
    if(!res.ok){ list.innerHTML = '<div class="empty-state">Could not load your chats.</div>'; return; }
    const conversations = await res.json();
    if(conversations.length === 0){
      list.innerHTML = '<div class="empty-state">No saved chats yet — ask Wura something to start one.</div>';
      return;
    }
    list.innerHTML = '';
    conversations.forEach(c => {
      const item = document.createElement('div');
      item.className = 'conversation-item' + (c.id === currentConversationId ? ' active' : '');
      item.textContent = c.title;
      item.addEventListener('click', () => openConversation(c.id));
      list.appendChild(item);
    });
  } catch(err){
    list.innerHTML = '<div class="empty-state">Could not load your chats.</div>';
  }
}

async function openConversation(id){
  try {
    const res = await fetch(`/api/assistant/conversations/${id}/messages`, {
      headers: { 'Authorization': 'Bearer ' + authToken }
    });
    if(!res.ok) return;
    const messages = await res.json();
    currentConversationId = id;
    chatHistory = [];
    assistantMessages.innerHTML = '';
    messages.forEach(m => {
      addMessage(m.content, m.role === 'user' ? 'user' : 'bot', m.role === 'assistant' ? m.source : null);
      chatHistory.push({ role: m.role, content: m.content });
    });
    viewingHistory = false;
    showChatView();
  } catch(err){
    // chat still usable even if this fails
  }
}

document.getElementById('assistantHistoryBtn').addEventListener('click', () => {
  viewingHistory = !viewingHistory;
  if(viewingHistory){ showConversationList(); loadConversationList(); }
  else { showChatView(); }
});

document.getElementById('btnNewChat').addEventListener('click', () => {
  currentConversationId = null;
  chatHistory = [];
  assistantMessages.innerHTML = '';
  addMessage("Mbolo! 👋 I'm Wura, your local guide for the Tropicana area. Ask me things like \"where can I get fuel near here\" or \"any good restaurants close by\" and I'll point you to real places on this map.", 'bot');
  viewingHistory = false;
  showChatView();
});