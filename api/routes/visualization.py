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
        #info {
            position: fixed; top: 16px; left: 16px; background: rgba(10,10,10,0.95);
            padding: 16px 20px; border-radius: 10px; font-size: 13px; z-index: 10;
            border: 1px solid #333; max-width: 460px; max-height: 85vh;
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
    </style>
</head>
<body>
    <div id="info"><h3>Global Ontology Engine</h3><p>Click any entity to see relationships and source articles</p></div>
    <div id="stats"></div>
    <div id="legend">
        <div class="item"><div class="dot" style="background:#4fc3f7"></div> Entity</div>
        <div class="item"><div class="dot" style="background:#ff7043"></div> Event</div>
        <div class="item"><div class="dot" style="background:#78909c;border-radius:2px"></div> Article</div>
    </div>
    <div id="graph"></div>
    <script>
        const TYPE_COLORS = {
            Person: '#42a5f5', Organization: '#ab47bc', Country: '#66bb6a',
            Location: '#8d6e63', Event: '#ff7043', Policy: '#ffa726',
            Technology: '#26c6da', Economic_Indicator: '#ffee58',
            Military_Asset: '#ef5350', Resource: '#9ccc65',
        };
        const LABEL_COLORS = { Entity: '#4fc3f7', Event: '#ff7043', Article: '#78909c' };
        const SHAPES = { Entity: 'dot', Event: 'diamond', Article: 'box' };

        fetch('/api/graph').then(r => r.json()).then(data => {
            // Only count visible edges (exclude EVIDENCES/EVIDENCES_REL)
            const visibleEdges = data.edges.filter(e =>
                e.type !== 'EVIDENCES' && e.type !== 'EVIDENCES_REL'
            );
            const edgeCount = {};
            visibleEdges.forEach(e => {
                if (e.from) edgeCount[e.from] = (edgeCount[e.from] || 0) + 1;
                if (e.to) edgeCount[e.to] = (edgeCount[e.to] || 0) + 1;
            });
            const maxEdges = Math.max(1, ...Object.values(edgeCount));

            const nodes = data.nodes.map(n => {
                const label = n.labels[0];
                const name = n.props.name || n.props.title || n.props.url || '?';
                const count = edgeCount[n.id] || 0;
                const isArticle = label === 'Article';
                const isEvent = label === 'Event';
                const entityType = n.props.type || '';
                const color = isArticle ? '#78909c' : isEvent ? '#ff7043' :
                              TYPE_COLORS[entityType] || '#4fc3f7';
                const size = isArticle ? 6 : 10 + (count / maxEdges) * 40;
                return {
                    id: n.id,
                    label: name.length > 35 ? name.slice(0, 35) + '...' : name,
                    fullLabel: name, group: label,
                    color: { background: color, border: color,
                             highlight: { background: '#fff', border: color } },
                    shape: SHAPES[label] || 'dot',
                    size, font: {
                        color: '#fff',
                        size: isArticle ? 0 : Math.max(10, 9 + (count / maxEdges) * 9)
                    },
                    props: n.props, nodeLabel: label, edgeCount: count,
                    sources: n.sources || [], entityType,
                    hidden: isArticle || count === 0,
                };
            });

            const edges = data.edges.filter(e => {
                // Hide EVIDENCES edges by default (articles are hidden)
                return e.type !== 'EVIDENCES' && e.type !== 'EVIDENCES_REL';
            }).map((e, i) => ({
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

            document.getElementById('stats').textContent =
                nodes.filter(n => !n.hidden).length + ' nodes, ' + edges.length + ' edges';

            const container = document.getElementById('graph');
            const network = new vis.Network(container, {
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
                    html += '<span class="tag">' + node.edgeCount + ' connections</span></p>';

                    // Find connected relationships
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

                    // Source articles
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

                } else if (node.nodeLabel === 'Article') {
                    html += '<p><span class="tag">Article</span></p>';
                    if (node.props.title) html += '<p><a href="' + node.props.url + '" target="_blank">' + node.props.title + '</a></p>';
                    if (node.props.source) html += '<p><b>Source:</b> ' + node.props.source + '</p>';
                    if (node.props.pub_date) html += '<p><b>Published:</b> ' + node.props.pub_date + '</p>';
                }

                info.innerHTML = html;
            });
        });
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
