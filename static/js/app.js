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

assistantFab.addEventListener('click', () => assistantPanel.classList.toggle('show'));
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
    const response = await fetch('/api/assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: chatHistory })
    });
    const data = await response.json();
    typing.remove();

    addMessage(data.reply, 'bot', data.source);
    chatHistory.push({ role:'user', content: text });
    chatHistory.push({ role:'assistant', content: data.reply });
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