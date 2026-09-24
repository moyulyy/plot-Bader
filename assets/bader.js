const resultData = window.BADER_RESULT_DATA || {};
const groupNames = window.BADER_GROUP_NAMES || [];
const atoms = resultData.charge_data || [];
const viewers = {};

const elementColors = {
    H: '#FFFFFF', He: '#D9FFFF', Li: '#CC80FF', Be: '#C2FF00',
    B: '#FFB5B5', C: '#909090', N: '#3050F8', O: '#FF0D0D',
    F: '#90E050', Ne: '#B3E3F5', Na: '#AB5CF2', Mg: '#8AFF00',
    Al: '#BFA6A6', Si: '#F0C8A0', P: '#FF8000', S: '#FFFF30',
    Cl: '#1FF01F', Ar: '#80D1E3', K: '#8F40D4', Ca: '#3DFF00',
    Sc: '#E6E6E6', Ti: '#BFC2C7', V: '#A6A6AB', Cr: '#8A99C7',
    Mn: '#9C7AC7', Fe: '#E06633', Co: '#F090A0', Ni: '#50D050',
    Cu: '#C88033', Zn: '#7D80B0', Ga: '#C28F8F', Ge: '#668F8F',
    As: '#BD80E3', Se: '#FFA100', Br: '#A62929', Kr: '#5CB8D1',
    Rb: '#702EB0', Sr: '#00FF00', Y: '#94FFFF', Zr: '#94E0E0',
    Nb: '#73C2C9', Mo: '#54B5B5', Tc: '#3B9E9E', Ru: '#248F8F',
    Rh: '#0A7D8C', Pd: '#006985', Ag: '#C0C0C0', Cd: '#FFD98F',
    In: '#A67573', Sn: '#668080', Sb: '#9E63B5', Te: '#D47A00',
    I: '#940094', Xe: '#429EB0', Cs: '#57178F', Ba: '#00C900',
    La: '#70D4FF', Ce: '#FFFFC7', Pt: '#D0D0E0', Au: '#FFD123',
    Pb: '#575961', Bi: '#9E4FB5', U: '#008FFF'
};

const viewerConfigs = {
    'viewer-index': { title: '原子序号', labelType: 'index' },
    'viewer-type': { title: '元素类型', labelType: 'type' },
    'viewer-charge': { title: 'Bader 电荷差（Δq）', labelType: 'charge' }
};

document.addEventListener('DOMContentLoaded', () => {
    initViewers();
    generateLegend();
    initGrouping();
    window.addEventListener('resize', debounceLayoutRefresh, { passive: true });
});

function initViewers() {
    if (!atoms.length) return;
    if (typeof window.$3Dmol === 'undefined') {
        renderViewerPlaceholders();
        return;
    }
    const xyzData = buildXYZData(atoms);
    Object.keys(viewerConfigs).forEach((containerId) => {
        initViewer(containerId, xyzData, viewerConfigs[containerId]);
    });
    requestAnimationFrame(() => {
        refreshViewerLayout();
        window.setTimeout(() => { refreshViewerLayout(); }, 120);
    });
}

function renderViewerPlaceholders() {
    ['viewer-index', 'viewer-type', 'viewer-charge'].forEach((id) => {
        const container = document.getElementById(id);
        if (!container) return;
        container.innerHTML = '<div class="bc-viewer-placeholder">未检测到可用的 3Dmol.js，本页仍保留结构数据与统计结果，但三维结构视图无法初始化。</div>';
    });
}

function buildXYZData(atomList) {
    const lines = [String(atomList.length), 'Bader structure'];
    atomList.forEach((atom) => {
        lines.push(`${atom.atom} ${Number(atom.loc_x).toFixed(6)} ${Number(atom.loc_y).toFixed(6)} ${Number(atom.loc_z).toFixed(6)}`);
    });
    return lines.join('\n');
}

function initViewer(containerId, xyzData, config) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const viewer = window.$3Dmol.createViewer(container, { backgroundColor: '#f5f7fa' });
    viewer.addModel(xyzData, 'xyz');
    applyElementStyles(viewer);
    addReferenceGrid(viewer);
    addLatticeOverlay(viewer);
    addDefaultLabels(viewer, config.labelType);
    viewer.zoomTo();
    viewer.render();
    viewers[containerId] = viewer;
}

function applyElementStyles(viewer) {
    const uniqueElements = [...new Set(atoms.map((atom) => atom.atom))];
    uniqueElements.forEach((element) => {
        const color = getElementColor(element);
        viewer.setStyle({ elem: element }, {
            stick: { radius: 0.12, color },
            sphere: { scale: 0.25, color }
        });
    });
}

function addLatticeOverlay(viewer) {
    const latticeVectors = resultData.lattice_vectors;
    if (!Array.isArray(latticeVectors) || latticeVectors.length !== 3) return;
    const origin = { x: 0, y: 0, z: 0 };
    const a = vectorToPoint(latticeVectors[0]);
    const b = vectorToPoint(latticeVectors[1]);
    const c = vectorToPoint(latticeVectors[2]);
    const ab = addPoints(a, b);
    const ac = addPoints(a, c);
    const bc = addPoints(b, c);
    const abc = addPoints(ab, c);
    const edges = [
        [origin, a], [origin, b], [origin, c],
        [a, ab], [a, ac], [b, ab], [b, bc],
        [c, ac], [c, bc], [ab, abc], [ac, abc], [bc, abc],
    ];
    edges.forEach(([start, end]) => {
        viewer.addLine({ start, end, color: 'black', linewidth: 1.5, dashed: false });
    });
    addAxisMarker(viewer, origin, normalizeAndScalePoint(a, 3.0), 'a');
    addAxisMarker(viewer, origin, normalizeAndScalePoint(b, 3.0), 'b');
    addAxisMarker(viewer, origin, normalizeAndScalePoint(c, 3.0), 'c');
}

function addReferenceGrid(viewer) {
    const bounds = getStructureBounds();
    if (!bounds) return;
    const z = bounds.minZ - Math.max(0.8, bounds.spanZ * 0.1);
    const gridColor = '#d4dbe5';
    const xStep = bounds.spanX > 0 ? Math.max(bounds.spanX / 6, 1) : 1;
    const yStep = bounds.spanY > 0 ? Math.max(bounds.spanY / 6, 1) : 1;
    for (let x = bounds.minX; x <= bounds.maxX + 1e-8; x += xStep) {
        viewer.addLine({ start: { x, y: bounds.minY, z }, end: { x, y: bounds.maxY, z }, color: gridColor, linewidth: 0.6, dashed: false });
    }
    for (let y = bounds.minY; y <= bounds.maxY + 1e-8; y += yStep) {
        viewer.addLine({ start: { x: bounds.minX, y, z }, end: { x: bounds.maxX, y, z }, color: gridColor, linewidth: 0.6, dashed: false });
    }
}

function getStructureBounds() {
    if (!atoms.length) return null;
    const xs = atoms.map(a => Number(a.loc_x));
    const ys = atoms.map(a => Number(a.loc_y));
    const zs = atoms.map(a => Number(a.loc_z));
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const minZ = Math.min(...zs), maxZ = Math.max(...zs);
    return { minX, maxX, minY, maxY, minZ, maxZ, spanX: Math.max(maxX - minX, 1), spanY: Math.max(maxY - minY, 1), spanZ: Math.max(maxZ - minZ, 1) };
}

function addAxisMarker(viewer, origin, vectorEnd, label) {
    viewer.addArrow({ start: origin, end: vectorEnd, radius: 0.08, color: 'black' });
    viewer.addLabel(label, { position: offsetPoint(vectorEnd, 0.2), fontSize: 14, fontColor: '#111827', backgroundColor: 'rgba(255,255,255,0.92)', showBackground: true, backgroundOpacity: 0.92, inFront: true });
}

function vectorToPoint(v) { return { x: Number(v[0]), y: Number(v[1]), z: Number(v[2]) }; }
function addPoints(l, r) { return { x: Number(l.x) + Number(r.x), y: Number(l.y) + Number(r.y), z: Number(l.z) + Number(r.z) }; }
function normalizeAndScalePoint(p, len) {
    const norm = Math.sqrt((Number(p.x) ** 2) + (Number(p.y) ** 2) + (Number(p.z) ** 2));
    if (!norm) return { x: 0, y: 0, z: 0 };
    const scale = len / norm;
    return { x: Number(p.x) * scale, y: Number(p.y) * scale, z: Number(p.z) * scale };
}
function offsetPoint(p, off) { return { x: Number(p.x) + off, y: Number(p.y) + off, z: Number(p.z) + off }; }

function addDefaultLabels(viewer, labelType) {
    atoms.forEach((atom) => {
        viewer.addLabel(buildLabelText(atom, labelType), {
            position: { x: Number(atom.loc_x), y: Number(atom.loc_y), z: Number(atom.loc_z) },
            fontSize: 12,
            fontColor: getLabelColor(atom, labelType),
            backgroundColor: 'rgba(255,255,255,0.82)',
            showBackground: true,
            backgroundOpacity: 0.82,
            inFront: true
        });
    });
}

function buildLabelText(atom, labelType) {
    if (labelType === 'index') return String(atom.index);
    if (labelType === 'type') return atom.atom;
    return Number(atom.delta_charge).toFixed(2);
}

function getLabelColor(atom, labelType) {
    if (labelType === 'type') return getElementColor(atom.atom);
    if (labelType === 'charge') return Number(atom.delta_charge) >= 0 ? '#b91c1c' : '#1d4ed8';
    return '#111827';
}

function refreshViewerLayout() {
    Object.values(viewers).forEach((v) => { if (v && typeof v.resize === 'function') { v.resize(); v.render(); } });
}
let layoutRefreshTimer = null;
function debounceLayoutRefresh() { window.clearTimeout(layoutRefreshTimer); layoutRefreshTimer = window.setTimeout(refreshViewerLayout, 80); }

function generateLegend() {
    const container = document.getElementById('legend-items');
    if (!container || !atoms.length) return;
    const uniqueElements = [...new Set(atoms.map(a => a.atom))].sort((l, r) => l.localeCompare(r, 'zh-CN'));
    uniqueElements.forEach((element) => {
        const item = document.createElement('div');
        item.className = 'bc-legend-item';
        item.innerHTML = `<div class="bc-legend-color" style="background-color:${getElementColor(element)}"></div><span>${element}</span>`;
        container.appendChild(item);
    });
}

function getElementColor(element) { return elementColors[element] || '#7c8798'; }

/* ---------- grouping ---------- */
function initGrouping() {
    const modeSelect = document.getElementById('grouping-mode');
    const zThresholdInput = document.getElementById('z-threshold-input');
    if (!modeSelect) return;

    document.querySelectorAll('.bc-group-checkbox input[type="checkbox"]').forEach((cb) => {
        cb.addEventListener('change', () => { if (modeSelect.value === 'manual') { renderGroupOptions(); updateGroupingSummary(); } });
    });
    modeSelect.addEventListener('change', () => { syncZThresholdVisibility(); renderGroupOptions(); updateGroupingSummary(); });
    if (zThresholdInput) {
        zThresholdInput.addEventListener('input', () => { if (modeSelect.value === 'z-threshold') { renderGroupOptions(); updateGroupingSummary(); } });
    }
    syncZThresholdVisibility();
    renderGroupOptions();
    updateGroupingSummary();
}

function syncZThresholdVisibility() {
    const mode = document.getElementById('grouping-mode')?.value;
    const block = document.getElementById('z-threshold-block');
    if (!block) return;
    block.hidden = mode !== 'z-threshold';
}

function renderGroupOptions() {
    const container = document.getElementById('group-selection-container');
    const modeSelect = document.getElementById('grouping-mode');
    if (!container || !modeSelect) return;
    const previousSelected = new Set([...container.querySelectorAll('.bc-group-selection-checkbox:checked')].map(c => c.value));
    const options = getCurrentGroups();
    container.innerHTML = '';
    if (!options.length) {
        container.innerHTML = `<div class="bc-selection-option">${modeSelect.value === 'z-threshold' ? '请输入 Z 阈值后生成分组。' : '当前没有可选分组。'}</div>`;
        renderGroupSummaryRows([]);
        clearRowHighlights();
        setSummaryCounts([], []);
        return;
    }
    options.forEach((opt) => {
        const label = document.createElement('label');
        label.className = 'bc-selection-option';
        label.innerHTML = `<input type="checkbox" class="bc-group-selection-checkbox" value="${escapeHtml2(opt.value)}"><span>${escapeHtml2(opt.label)}</span>`;
        const cb = label.querySelector('.bc-group-selection-checkbox');
        if (cb && previousSelected.has(opt.value)) cb.checked = true;
        container.appendChild(label);
    });
    container.querySelectorAll('.bc-group-selection-checkbox').forEach(cb => cb.addEventListener('change', updateGroupingSummary));
}

function getCurrentGroups() {
    const mode = document.getElementById('grouping-mode')?.value;
    if (mode === 'manual') return groupNames.map(n => ({ value: n, label: n }));
    if (mode === 'element') return [...new Set(atoms.map(a => a.atom))].sort((l, r) => l.localeCompare(r, 'zh-CN')).map(e => ({ value: e, label: e }));
    if (mode === 'z-threshold') {
        const t = Number(document.getElementById('z-threshold-input')?.value);
        if (!Number.isFinite(t)) return [];
        return [{ value: 'lt', label: `< ${t}` }, { value: 'ge', label: `≥ ${t}` }];
    }
    return [];
}

function updateGroupingSummary() {
    const selected = [...document.querySelectorAll('.bc-group-selection-checkbox:checked')].map(c => c.value);
    const summaries = buildGroupSummaries(selected);
    const matched = dedupeAtoms(summaries.flatMap(s => s.atoms));
    renderGroupSummaryRows(summaries);
    highlightRows(matched);
    setSummaryCounts(selected, matched);
}

function buildGroupSummaries(selected) {
    const mode = document.getElementById('grouping-mode')?.value;
    if (!selected.length) return [];
    if (mode === 'manual') {
        const assignments = readManualAssignments();
        return selected.map(name => { const matched = atoms.filter(a => assignments[name]?.has(String(a.index))); return makeSummary(name, matched); });
    }
    if (mode === 'element') return selected.map(e => makeSummary(e, atoms.filter(a => a.atom === e)));
    if (mode === 'z-threshold') {
        const t = Number(document.getElementById('z-threshold-input')?.value);
        if (!Number.isFinite(t)) return [];
        return selected.map(key => { const matched = atoms.filter(a => key === 'lt' ? Number(a.loc_z) < t : Number(a.loc_z) >= t); return makeSummary(key === 'lt' ? `< ${t}` : `≥ ${t}`, matched); });
    }
    return [];
}

function readManualAssignments() {
    const a = {};
    groupNames.forEach(n => { a[n] = new Set(); });
    document.querySelectorAll('.bc-group-checkbox input[type="checkbox"]:checked').forEach(cb => {
        if (!a[cb.dataset.groupName]) a[cb.dataset.groupName] = new Set();
        a[cb.dataset.groupName].add(cb.dataset.atomIndex);
    });
    return a;
}

function makeSummary(label, matched) { return { label, atoms: matched, atomCount: matched.length, deltaSum: matched.reduce((t, a) => t + Number(a.delta_charge), 0) }; }

function renderGroupSummaryRows(summaries) {
    const tbody = document.getElementById('group-summary-body');
    if (!tbody) return;
    if (!summaries.length) { tbody.innerHTML = '<tr><td colspan="3">请选择分组后查看统计结果。</td></tr>'; return; }
    tbody.innerHTML = summaries.map(s => `<tr><td>${escapeHtml2(s.label)}</td><td>${s.atomCount}</td><td>${s.deltaSum.toFixed(6)}</td></tr>`).join('');
}

function setSummaryCounts(selected, matched) {
    const sg = document.getElementById('selected-group-count');
    const ma = document.getElementById('matched-atom-count');
    const md = document.getElementById('matched-delta-sum');
    if (!sg || !ma || !md) return;
    sg.textContent = String(selected.length);
    ma.textContent = String(matched.length);
    md.textContent = matched.reduce((t, a) => t + Number(a.delta_charge), 0).toFixed(6);
}

function clearRowHighlights() { document.querySelectorAll('.bc-atom-row').forEach(r => r.classList.remove('bc-is-highlighted')); }
function highlightRows(matched) {
    const ids = new Set(matched.map(a => String(a.index)));
    document.querySelectorAll('.bc-atom-row').forEach(r => r.classList.toggle('bc-is-highlighted', ids.has(r.dataset.index)));
}
function dedupeAtoms(list) { const m = new Map(); list.forEach(a => m.set(String(a.index), a)); return [...m.values()]; }

function escapeHtml2(v) { return String(v).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }

function toggleFullscreen(panelId) {
    const panel = document.getElementById(panelId);
    if (!panel) return;
    panel.classList.toggle('bc-fullscreen');
    setTimeout(() => {
        const c = panel.querySelector('.bc-viewer-container');
        if (!c) return;
        const v = viewers[c.id];
        if (v) { v.resize(); v.render(); }
    }, 120);
}
window.toggleFullscreen = toggleFullscreen;
