from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Global Ontology Engine</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0a; color: #fff; }
        #graph { width: 100vw; height: 100vh; }

        #toolbar {
            position: fixed; top: 0; left: 0; right: 0; z-index: 20;
            background: rgba(10,10,10,0.97); border-bottom: 1px solid #222;
            padding: 10px 20px; display: flex; align-items: center; gap: 12px;
            flex-wrap: wrap; backdrop-filter: blur(10px);
        }
        #toolbar label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
        #toolbar input[type="text"] {
            padding: 6px 10px; border-radius: 6px; border: 1px solid #333;
            background: #111; color: #fff; font-size: 13px; width: 180px; outline: none;
        }
        #toolbar input[type="text"]:focus { border-color: #4fc3f7; }
        #toolbar select {
            padding: 6px 8px; border-radius: 6px; border: 1px solid #333;
            background: #111; color: #fff; font-size: 12px; outline: none;
        }
        #toolbar input[type="range"] { width: 100px; accent-color: #4fc3f7; }
        #toolbar .range-val { font-size: 12px; color: #4fc3f7; min-width: 30px; }
        #toolbar button {
            padding: 6px 14px; border-radius: 6px; border: none;
            background: #1565c0; color: #fff; font-size: 12px; cursor: pointer;
            font-weight: 500;
        }
        #toolbar button:hover { background: #1976d2; }
        #toolbar .divider { width: 1px; height: 24px; background: #333; }

        #info {
            position: fixed; top: 70px; left: 16px; background: rgba(10,10,10,0.95);
            padding: 16px 20px; border-radius: 10px; font-size: 13px; z-index: 10;
            border: 1px solid #333; max-width: 460px; max-height: 75vh;
            overflow-y: auto; backdrop-filter: blur(10px);
        }
        #info h3 { margin-bottom: 8px; color: #4fc3f7; font-size: 15px; }
        #info p { color: #ccc; margin: 3px 0; line-height: 1.5; }
        #info .tag { display: inline-block; background: #1a3a4a; color: #4fc3f7;
            padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px 2px; }
        #info .tag.causal { background: #3a1a1a; color: #ef9a9a; }
        #info .tag.temporal { background: #1a3a1a; color: #a5d6a7; }
        #info a { color: #81d4fa; text-decoration: none; }
        #info a:hover { text-decoration: underline; }
        #info .source-item { padding: 6px 0; border-bottom: 1px solid #1a1a1a; }
        #info .source-item:last-child { border-bottom: none; }
        #info .source-badge { font-size: 10px; background: #222; padding: 1px 6px;
            border-radius: 3px; color: #aaa; margin-left: 4px; }
        #info .section-title { margin-top: 10px; margin-bottom: 4px; color: #ffb74d;
            font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        #info .rel-item { padding: 4px 0; color: #e0e0e0; font-size: 12px; }
        #info .rel-arrow { color: #4fc3f7; margin: 0 4px; }

        #stats {
            position: fixed; bottom: 16px; left: 16px; background: rgba(10,10,10,0.9);
            padding: 8px 14px; border-radius: 8px; font-size: 12px; color: #888;
            border: 1px solid #222;
        }
        #legend {
            position: fixed; bottom: 16px; right: 16px; background: rgba(10,10,10,0.9);
            padding: 10px 14px; border-radius: 8px; font-size: 11px; color: #aaa;
            border: 1px solid #222;
        }
        #legend .item { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
        #legend .dot { width: 10px; height: 10px; border-radius: 50%; }
        .loading {
            position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
            color: #4fc3f7; font-size: 14px; z-index: 30;
        }
    </style>
</head>
<body>
    <div id="toolbar">
        <label>Search</label>
        <input type="text" id="search" placeholder="Entity name..." />
        <div class="divider"></div>
        <label>Type</label>
        <select id="entityType">
            <option value="">All Types</option>
            <option value="Person">Person</option>
            <option value="Organization">Organization</option>
            <option value="Country">Country</option>
            <option value="Location">Location</option>
            <option value="Policy">Policy</option>
            <option value="Technology">Technology</option>
            <option value="Economic_Indicator">Economic Indicator</option>
            <option value="Military_Asset">Military Asset</option>
            <option value="Resource">Resource</option>
        </select>
        <div class="divider"></div>
        <label>Nodes</label>
        <input type="range" id="limitSlider" min="20" max="500" value="100" />
        <span class="range-val" id="limitVal">100</span>
        <div class="divider"></div>
        <label>Min Connections</label>
        <input type="range" id="minConnSlider" min="0" max="10" value="1" />
        <span class="range-val" id="minConnVal">1</span>
        <div class="divider"></div>
        <button onclick="loadGraph()">Apply</button>
        <a href="/chat" style="color:#666;font-size:12px;text-decoration:none;margin-left:auto;">Chat →</a>
    </div>

    <div id="info"><h3>Global Ontology Engine</h3><p>Click any entity to see relationships and source articles</p></div>
    <div id="stats"></div>
    <div id="legend">
        <div class="item"><div class="dot" style="background:#42a5f5"></div> Person</div>
        <div class="item"><div class="dot" style="background:#ab47bc"></div> Organization</div>
        <div class="item"><div class="dot" style="background:#66bb6a"></div> Country</div>
        <div class="item"><div class="dot" style="background:#8d6e63"></div> Location</div>
        <div class="item"><div class="dot" style="background:#ff7043;border-radius:2px"></div> Event</div>
    </div>
    <div id="graph"></div>
    <div id="loadingIndicator" class="loading">Loading graph...</div>

    <script>
        const TYPE_COLORS = {
            Person: '#42a5f5', Organization: '#ab47bc', Country: '#66bb6a',
            Location: '#8d6e63', Event: '#ff7043', Policy: '#ffa726',
            Technology: '#26c6da', Economic_Indicator: '#ffee58',
            Military_Asset: '#ef5350', Resource: '#9ccc65',
        };
        const SHAPES = { Entity: 'dot', Event: 'diamond' };

        let network = null;

        // Slider live updates
        document.getElementById('limitSlider').oninput = e =>
            document.getElementById('limitVal').textContent = e.target.value;
        document.getElementById('minConnSlider').oninput = e =>
            document.getElementById('minConnVal').textContent = e.target.value;

        // Enter key triggers search
        document.getElementById('search').addEventListener('keydown', e => {
            if (e.key === 'Enter') loadGraph();
        });

        // Fetch stats
        fetch('/api/graph/stats').then(r => r.json()).then(stats => {
            document.getElementById('stats').textContent =
                `Graph: ${stats.total_entities} entities, ${stats.total_relationships} relationships, ` +
                `${stats.total_events} events, ${stats.total_articles} articles`;
        });

        function loadGraph() {
            const search = document.getElementById('search').value.trim();
            const entityType = document.getElementById('entityType').value;
            const limit = document.getElementById('limitSlider').value;
            const minConn = document.getElementById('minConnSlider').value;

            const params = new URLSearchParams({ limit, min_connections: minConn });
            if (search) params.set('search', search);
            if (entityType) params.set('entity_type', entityType);

            document.getElementById('loadingIndicator').style.display = 'block';

            fetch('/api/graph?' + params).then(r => r.json()).then(data => {
                document.getElementById('loadingIndicator').style.display = 'none';

                const maxDegree = Math.max(1, ...data.nodes.map(n => n.degree || 0));

                const nodes = data.nodes.map(n => {
                    const label = n.labels[0];
                    const name = n.props.name || n.props.title || '?';
                    const degree = n.degree || 0;
                    const isEvent = label === 'Event';
                    const entityType = n.props.type || '';
                    const color = isEvent ? '#ff7043' : TYPE_COLORS[entityType] || '#4fc3f7';
                    const size = isEvent ? 12 : 10 + (degree / maxDegree) * 40;
                    return {
                        id: n.id,
                        label: name.length > 35 ? name.slice(0, 35) + '...' : name,
                        fullLabel: name, group: label,
                        color: { background: color, border: color,
                                 highlight: { background: '#fff', border: color } },
                        shape: SHAPES[label] || 'dot',
                        size, font: {
                            color: '#fff',
                            size: Math.max(10, 9 + (degree / maxDegree) * 9)
                        },
                        props: n.props, nodeLabel: label, degree,
                        sources: n.sources || [], entityType,
                    };
                });

                const edges = data.edges.map((e, i) => ({
                    id: i, from: e.from, to: e.to,
                    label: e.props?.type || e.type,
                    color: {
                        color: e.props?.causal ? '#ef5350' : '#444',
                        highlight: '#4fc3f7'
                    },
                    font: { color: '#999', size: 10, strokeWidth: 0 },
                    arrows: 'to', smooth: { type: 'continuous' },
                    width: e.props?.causal ? 2 : 1,
                    dashes: e.type === 'INVOLVED_IN' ? [5, 5] : false,
                }));

                // Update stats
                const statsEl = document.getElementById('stats');
                fetch('/api/graph/stats').then(r => r.json()).then(stats => {
                    statsEl.textContent =
                        `Showing ${nodes.length} nodes, ${edges.length} edges — ` +
                        `Graph total: ${stats.total_entities} entities, ${stats.total_articles} articles`;
                });

                // Destroy old network
                if (network) network.destroy();

                const container = document.getElementById('graph');
                network = new vis.Network(container, {
                    nodes: new vis.DataSet(nodes),
                    edges: new vis.DataSet(edges),
                }, {
                    physics: {
                        solver: 'forceAtlas2Based',
                        forceAtlas2Based: { gravitationalConstant: -120, springLength: 150, damping: 0.5 },
                        stabilization: { iterations: 300 },
                    },
                    interaction: { hover: true, tooltipDelay: 100 },
                });

                network.on('click', params => {
                    const info = document.getElementById('info');
                    if (params.nodes.length === 0) {
                        info.innerHTML = '<h3>Global Ontology Engine</h3><p>Click any entity to see relationships and source articles</p>';
                        return;
                    }
                    const node = nodes.find(n => n.id === params.nodes[0]);
                    let html = '<h3>' + node.fullLabel + '</h3>';

                    if (node.nodeLabel === 'Entity') {
                        html += '<p><span class="tag">' + (node.entityType || 'Entity') + '</span>';
                        html += '<span class="tag">' + node.degree + ' connections</span></p>';

                        const rels = data.edges.filter(e =>
                            (e.from === node.id || e.to === node.id) &&
                            e.type === 'RELATES_TO' && e.props?.type
                        );
                        if (rels.length) {
                            html += '<div class="section-title">Relationships</div>';
                            rels.forEach(r => {
                                const other = nodes.find(n => n.id === (r.from === node.id ? r.to : r.from));
                                if (!other) return;
                                const isSource = r.from === node.id;
                                const arrow = isSource ? '→' : '←';
                                html += '<div class="rel-item">';
                                if (r.props.causal) html += '<span class="tag causal">causal</span> ';
                                if (r.props.temporal) html += '<span class="tag temporal">' + r.props.temporal + '</span> ';
                                html += node.fullLabel + ' <span class="rel-arrow">' + arrow + ' ' + r.props.type + ' ' + arrow + '</span> ' + other.fullLabel;
                                html += '</div>';
                            });
                        }

                        if (node.sources && node.sources.length) {
                            html += '<div class="section-title">Source Articles (' + node.sources.length + ')</div>';
                            node.sources.forEach(s => {
                                html += '<div class="source-item">';
                                html += '<a href="' + s.url + '" target="_blank">' + s.title + '</a>';
                                html += '<span class="source-badge">' + s.source + '</span>';
                                if (s.pub_date) html += '<span class="source-badge">' + s.pub_date + '</span>';
                                html += '</div>';
                            });
                        }

                    } else if (node.nodeLabel === 'Event') {
                        html += '<p><span class="tag">Event</span>';
                        if (node.props.status) html += '<span class="tag">' + node.props.status + '</span>';
                        if (node.props.date) html += '<span class="tag temporal">' + node.props.date + '</span>';
                        html += '</p>';

                        if (node.sources && node.sources.length) {
                            html += '<div class="section-title">Source Articles (' + node.sources.length + ')</div>';
                            node.sources.forEach(s => {
                                html += '<div class="source-item">';
                                html += '<a href="' + s.url + '" target="_blank">' + s.title + '</a>';
                                html += '<span class="source-badge">' + s.source + '</span>';
                                html += '</div>';
                            });
                        }
                    }

                    info.innerHTML = html;
                });
            }).catch(err => {
                document.getElementById('loadingIndicator').style.display = 'none';
                console.error('Failed to load graph:', err);
            });
        }

        // Load on startup
        loadGraph();
    </script>
</body>
</html>"""


@router.get("/chat", response_class=HTMLResponse)
def chat_page():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Graph Chat — Intelligence Assistant</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0a0a0a; color: #e0e0e0;
            display: flex; flex-direction: column; height: 100vh;
        }
        header {
            padding: 12px 20px; border-bottom: 1px solid #222;
            display: flex; align-items: center; gap: 12px;
            background: rgba(10,10,10,0.95); backdrop-filter: blur(10px);
        }
        header h1 { font-size: 16px; color: #4fc3f7; font-weight: 600; }
        header a { color: #666; font-size: 12px; text-decoration: none; }
        header a:hover { color: #4fc3f7; }
        #messages {
            flex: 1; overflow-y: auto; padding: 20px;
            display: flex; flex-direction: column; gap: 16px;
        }
        .msg {
            max-width: 720px; padding: 12px 16px; border-radius: 12px;
            line-height: 1.6; font-size: 14px; white-space: pre-wrap;
        }
        .msg.user {
            align-self: flex-end; background: #1a3a5c; color: #e3f2fd;
            border-bottom-right-radius: 4px;
        }
        .msg.assistant {
            align-self: flex-start; background: #1a1a1a; border: 1px solid #282828;
            border-bottom-left-radius: 4px;
        }
        .msg.assistant .cypher-tag {
            display: inline-block; background: #1a2a1a; color: #81c784;
            font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px;
            padding: 6px 10px; border-radius: 6px; margin-top: 8px;
            border: 1px solid #2a3a2a; word-break: break-all;
        }
        .msg.system {
            align-self: center; color: #666; font-size: 12px;
            font-style: italic; padding: 4px;
        }
        #input-area {
            padding: 12px 20px; border-top: 1px solid #222;
            display: flex; gap: 10px; background: rgba(10,10,10,0.95);
        }
        #input-area input {
            flex: 1; padding: 10px 14px; border-radius: 8px;
            border: 1px solid #333; background: #111; color: #fff;
            font-size: 14px; outline: none;
        }
        #input-area input:focus { border-color: #4fc3f7; }
        #input-area input::placeholder { color: #555; }
        #input-area button {
            padding: 10px 20px; border-radius: 8px; border: none;
            background: #1565c0; color: #fff; font-size: 14px;
            cursor: pointer; font-weight: 500;
        }
        #input-area button:hover { background: #1976d2; }
        #input-area button:disabled { background: #333; color: #666; cursor: not-allowed; }
        .typing { color: #666; font-style: italic; }
    </style>
</head>
<body>
    <header>
        <h1>Intelligence Graph Chat</h1>
        <a href="/">← Graph View</a>
    </header>
    <div id="messages">
        <div class="msg system">Ask questions about entities, relationships, events, and trends in the knowledge graph.</div>
    </div>
    <div id="input-area">
        <input id="q" type="text" placeholder="Ask about the knowledge graph..." autocomplete="off" />
        <button id="send" onclick="send()">Send</button>
    </div>
    <script>
        const msgs = document.getElementById('messages');
        const qInput = document.getElementById('q');
        const sendBtn = document.getElementById('send');
        let history = [];

        qInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !sendBtn.disabled) send(); });

        async function send() {
            const q = qInput.value.trim();
            if (!q) return;
            qInput.value = '';

            // User message
            addMsg('user', q);
            history.push({ role: 'user', content: q });

            // Typing indicator
            const typing = document.createElement('div');
            typing.className = 'msg assistant typing';
            typing.textContent = 'Thinking...';
            msgs.appendChild(typing);
            msgs.scrollTop = msgs.scrollHeight;
            sendBtn.disabled = true;

            try {
                const resp = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: q, history: history.slice(0, -1) }),
                });
                const data = await resp.json();
                typing.remove();

                let content = data.answer;
                addMsg('assistant', content, data.cypher);
                history.push({ role: 'assistant', content: data.answer });
            } catch (err) {
                typing.remove();
                addMsg('assistant', 'Error: ' + err.message);
            }
            sendBtn.disabled = false;
            qInput.focus();
        }

        function addMsg(role, text, cypher) {
            const div = document.createElement('div');
            div.className = 'msg ' + role;
            div.textContent = text;
            if (cypher && cypher !== 'NONE') {
                const tag = document.createElement('div');
                tag.className = 'cypher-tag';
                tag.textContent = cypher;
                div.appendChild(tag);
            }
            msgs.appendChild(div);
            msgs.scrollTop = msgs.scrollHeight;
        }
    </script>
</body>
</html>"""
