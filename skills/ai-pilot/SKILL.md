---
name: ai-pilot
version: 2.0.0
description: |
  Rend toute application pilotable par un agent IA via JSON RPC sémantique.
  Language-agnostic, framework-agnostic, transport-agnostic.

  Ce skill n'est PAS une migration de langage — il ajoute une couche de contrôle
  à une application EXISTANTE, quelle que soit sa technologie.

  Pattern universel en 3 couches :
    1. Transport  — canal bidirectionnel JSON (stdin/stdout, TCP, WebSocket, pipe…)
    2. Dispatcher — applique les commandes sur l'état de l'app (NO UI code)
    3. Arbre sémantique — snapshot read-only de l'UI (ids stables, pas de pixels)

  Éprouvé sur : application GUI native (egui/C++), plugins audio temps réel
  (CLAP/Rust) et outils CLI — les mêmes trois couches à chaque fois.

  Use when: "rendre pilotable", "ai rpc", "canal agent", "piloter par IA",
  "contrôle sémantique", "tester avec IA", "agent pilote", "ai-pilot",
  "introspection UI", "automatiser tests".
triggers:
  - rendre pilotable
  - canal agent
  - piloter par IA
  - contrôle sémantique
  - ai rpc
  - agent pilote
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

## Étape 0 — Identifier le type d'application

Lire les fichiers du projet pour répondre à trois questions :

**Q1 — Quel est le langage principal ?**
Rust / C++ / Python / TypeScript / Java / Go / autre

**Q2 — Quel est le type d'application ?**

| Type | Exemples | Transport recommandé |
|---|---|---|
| App standalone CLI ou GUI | app Rust/Python/Go avec `main()` | **stdin/stdout** |
| App GUI avec event loop | egui, Qt, SDL, Tk, wxWidgets | stdin/stdout **ou** TCP localhost |
| Plugin chargé dans un hôte | CLAP, VST3, LV2, extension navigateur | Named pipe (Win) / Unix socket (Lin/Mac) |
| App Electron / Node.js | desktop, IDE extension | **IPC** ou WebSocket |
| App Web (SPA) | React, Vue, Svelte | **WebSocket** |
| App mobile | Android (Kotlin/Java), iOS (Swift) | **TCP loopback** (`127.0.0.1`) |
| Jeu / moteur | Unity, Godot, Unreal | **WebSocket** ou TCP |

**Q3 — Où vit l'état de l'application ?**
Un struct central ? Un store global ? Des AtomicXxx ? Un bus d'événements ?
→ C'est ici que le dispatcher mutate, et ici que l'arbre lit.

---

## Protocole JSON (universel)

Une commande JSON par ligne → une réponse JSON par ligne.
Le champ `"cmd"` discrimine la variante. Réponse toujours `{"ok": true/false}`.

```json
{"cmd":"state_query"}
→ {"ok":true,"data":{"title":"Mon App","version":"1.2"}}

{"cmd":"ui_tree_dump"}
→ {"ok":true,"data":{"id":"root","role":"application","label":"Mon App","children":[...]}}

{"cmd":"param_set","id":"volume","value":0.8}
→ {"ok":true}

{"cmd":"param_get","id":"volume"}
→ {"ok":true,"data":{"value":0.8}}

{"cmd":"action","name":"save"}
→ {"ok":true}
```

Erreur : `{"ok":false,"error":"unknown param: foo"}`

**Commandes minimales** : `state_query` + `ui_tree_dump` + `param_get` + `param_set`
**Optionnelles** : `action`, `navigate`, `assert`, `screenshot`

---

## Nœud sémantique — la même structure dans tout langage

Chaque nœud a un `id` stable (chemin en dot notation), un `role` (type widget),
un `label` (texte affiché), et optionnellement `value`, `checked`, `children`.

**Rôles standards** : `application`, `panel`, `group`, `toolbar`,
`button`, `checkbox`, `slider`, `combobox`, `textfield`, `listitem`, `label`

### Rust
```rust
#[derive(serde::Serialize)]
pub struct SemanticNode {
    pub id: String,
    pub role: &'static str,
    pub label: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub value: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub checked: Option<bool>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub children: Vec<SemanticNode>,
}
```

### Python
```python
from dataclasses import dataclass, field

@dataclass
class SemanticNode:
    id: str
    role: str
    label: str
    value: str | None = None
    checked: bool | None = None
    children: list["SemanticNode"] = field(default_factory=list)

    def to_dict(self):
        d = {"id": self.id, "role": self.role, "label": self.label}
        if self.value is not None: d["value"] = self.value
        if self.checked is not None: d["checked"] = self.checked
        if self.children: d["children"] = [c.to_dict() for c in self.children]
        return d
```

### TypeScript
```typescript
interface SemanticNode {
  id: string;
  role: string;
  label: string;
  value?: string;
  checked?: boolean;
  children?: SemanticNode[];
}
```

### Java / Kotlin
```kotlin
data class SemanticNode(
    val id: String,
    val role: String,
    val label: String,
    val value: String? = null,
    val checked: Boolean? = null,
    val children: List<SemanticNode> = emptyList()
)
```

---

## Transport 1 — stdin/stdout (app standalone, toute langue)

Le plus simple. Démarrer l'app avec un flag `--ai-rpc`. Aucune dépendance réseau.

### Rust
```rust
// spawn() : appelé au démarrage si --ai-rpc dans les args
pub fn spawn() -> std::sync::mpsc::Receiver<AiRpcEnvelope> {
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::Builder::new().name("ai-rpc-stdin".into())
        .spawn(move || {
            use std::io::BufRead;
            for line in std::io::BufReader::new(std::io::stdin().lock()).lines().flatten() {
                let cmd = match serde_json::from_str::<AiCommand>(&line) {
                    Ok(c) => c,
                    Err(e) => { println!("{}", serde_json::to_string(&AiResponse::err(e.to_string())).unwrap()); continue; }
                };
                let (resp_tx, resp_rx) = std::sync::mpsc::sync_channel(1);
                if tx.send(AiRpcEnvelope { cmd, response_tx: resp_tx }).is_err() { break; }
                if let Ok(r) = resp_rx.recv() { println!("{}", serde_json::to_string(&r).unwrap()); }
            }
        }).expect("spawn");
    rx
}
// Drain une fois par frame, depuis le thread principal :
// while let Ok(env) = ai_rpc_rx.try_recv() { ... dispatch ... }
```

### Python
```python
import sys, json, threading, queue

def start_stdin_rpc(dispatch_fn) -> queue.Queue:
    q = queue.Queue()
    def loop():
        for line in sys.stdin:
            try:
                cmd = json.loads(line)
            except json.JSONDecodeError as e:
                print(json.dumps({"ok": False, "error": str(e)}), flush=True)
                continue
            resp_q = queue.Queue(maxsize=1)
            q.put((cmd, resp_q))
            resp = resp_q.get()
            print(json.dumps(resp), flush=True)
    threading.Thread(target=loop, daemon=True).start()
    return q
# Dans la boucle principale : drain q avec q.get_nowait()
```

---

## Transport 2 — TCP socket (universel, recommandé pour plugins et apps multi-instances)

Chaque instance écoute sur un port différent. L'agent se connecte par port.

### Python (serveur dans l'app)
```python
import socket, json, threading

def start_tcp_rpc(dispatch_fn, port: int = 17000):
    def serve():
        with socket.socket() as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", port))
            srv.listen(1)
            while True:
                conn, _ = srv.accept()
                threading.Thread(
                    target=_handle, args=(conn, dispatch_fn), daemon=True
                ).start()
    threading.Thread(target=serve, daemon=True).start()

def _handle(conn, dispatch_fn):
    with conn.makefile("rw") as f:
        for line in f:
            resp = dispatch_fn(json.loads(line.strip()))
            f.write(json.dumps(resp) + "\n")
            f.flush()
```

### TypeScript / Node.js (serveur)
```typescript
import net from 'net';

export function startTcpRpc(dispatch: (cmd: object) => object, port = 17000) {
  net.createServer((socket) => {
    let buf = '';
    socket.on('data', (data) => {
      buf += data.toString();
      const lines = buf.split('\n');
      buf = lines.pop() ?? '';
      for (const line of lines.filter(Boolean)) {
        const resp = dispatch(JSON.parse(line));
        socket.write(JSON.stringify(resp) + '\n');
      }
    });
  }).listen(port, '127.0.0.1');
}
```

### Rust (serveur TCP)
```rust
pub fn spawn_tcp(port: u16) -> std::sync::mpsc::Receiver<AiRpcEnvelope> {
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::Builder::new().name("ai-rpc-tcp".into())
        .spawn(move || {
            let listener = std::net::TcpListener::bind(("127.0.0.1", port))
                .expect("ai-rpc bind");
            for stream in listener.incoming().flatten() {
                let tx2 = tx.clone();
                std::thread::spawn(move || handle_stream(stream, tx2));
            }
        }).expect("spawn");
    rx
}
```

---

## Transport 3 — Named pipe / Unix socket (plugins, extensions)

Pour les composants chargés dans un hôte (pas accès à stdin).

### Rust (Windows named pipe)
```rust
// Pipe name: \\.\pipe\{app-id}-ai-rpc
// Transport named-pipe complet : à placer dans `ai_rpc/pipe_transport.rs`.
// Imports corrects windows-sys 0.52 :
//   PIPE_ACCESS_DUPLEX  → Win32::Storage::FileSystem
//   CreateNamedPipeW, ConnectNamedPipe, PIPE_TYPE_BYTE, PIPE_WAIT → Win32::System::Pipes
// Features Cargo.toml : Win32_Security, Win32_Storage_FileSystem, Win32_System_IO, Win32_System_Pipes
```

### Python (Unix socket — Linux/Mac)
```python
import socket, os, json, threading

SOCK_PATH = "/tmp/{app-id}-ai-rpc.sock"

def start_unix_rpc(dispatch_fn):
    if os.path.exists(SOCK_PATH): os.unlink(SOCK_PATH)
    def serve():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.bind(SOCK_PATH)
            s.listen(1)
            while True:
                conn, _ = s.accept()
                threading.Thread(target=_handle, args=(conn, dispatch_fn), daemon=True).start()
    threading.Thread(target=serve, daemon=True).start()
```

---

## Transport 4 — WebSocket (web apps, Electron, jeux)

```typescript
// Electron main process ou serveur Node.js dédié
import { WebSocketServer } from 'ws';

export function startWsRpc(dispatch: (cmd: object) => object, port = 17000) {
  const wss = new WebSocketServer({ port, host: '127.0.0.1' });
  wss.on('connection', (ws) => {
    ws.on('message', (raw) => {
      const resp = dispatch(JSON.parse(raw.toString()));
      ws.send(JSON.stringify(resp));
    });
  });
}
```

```python
# Agent (client WebSocket)
import websocket, json
ws = websocket.WebSocket()
ws.connect("ws://127.0.0.1:17000")
ws.send(json.dumps({"cmd": "ui_tree_dump"}))
tree = json.loads(ws.recv())
```

---

## Dispatcher — règles de conception

```
dispatch(state, cmd) → response
```

1. **Jamais de code UI** dans le dispatcher — pas de `draw_*`, `render_*`, widgets
2. **Jamais de panic** — toute erreur retourne `{"ok": false, "error": "..."}`
3. **Réutiliser le chemin existant** — si l'app a déjà une fonction `set_param(id, value)`, appeler celle-là
4. **Valider les bornes** — clamp sur range pour les valeurs numériques
5. **Thread de drain** — appeler le dispatcher depuis le thread qui possède l'état (main/GUI thread)

---

## Wiring dans la boucle principale

Le transport (thread séparé) envoie les enveloppes via une queue.
La boucle principale draine avant chaque rendu frame :

```
// Pseudo-code, même principe dans tout langage :
each_frame():
    while (env = queue.try_pop()):
        resp = dispatcher.dispatch(state, env.cmd)
        env.response_channel.send(resp)
    render(state)  // mutations sont visibles dans ce frame
```

---

## Agent Python universel (client)

Fonctionne avec stdin/stdout **ou** TCP — changer juste la connexion.

```python
import subprocess, socket, json

class AiPilot:
    """Client universel — stdin/stdout ou TCP."""

    @classmethod
    def via_subprocess(cls, cmd: list[str]) -> "AiPilot":
        proc = subprocess.Popen(cmd + ["--ai-rpc"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        return cls(proc.stdin, proc.stdout)

    @classmethod
    def via_tcp(cls, host="127.0.0.1", port=17000) -> "AiPilot":
        s = socket.create_connection((host, port))
        f = s.makefile("rw")
        return cls(f, f)

    def __init__(self, writer, reader):
        self._w, self._r = writer, reader

    def cmd(self, **kwargs) -> dict:
        self._w.write(json.dumps(kwargs) + "\n")
        self._w.flush()
        return json.loads(self._r.readline())

    # Helpers
    def state(self)         -> dict: return self.cmd(cmd="state_query")["data"]
    def tree(self)          -> dict: return self.cmd(cmd="ui_tree_dump")["data"]
    def get(self, id: str)  -> float: return self.cmd(cmd="param_get", id=id)["data"]["value"]
    def set(self, id: str, value: float): assert self.cmd(cmd="param_set", id=id, value=value)["ok"]
    def action(self, name: str): assert self.cmd(cmd="action", name=name)["ok"]

# Exemples :
# pilot = AiPilot.via_subprocess(["./my_app"])
# pilot = AiPilot.via_tcp(port=17001)           # composant chargé dans un hôte
# pilot.set("volume", 0.7)
# assert abs(pilot.get("volume") - 0.7) < 0.01
# tree = pilot.tree()   # → introspect toute l'UI
```

---

## Tests — template (4 tests minimum)

```python
def test_state_query_ok(pilot):
    s = pilot.state()
    assert "title" in s or "plugin" in s

def test_ui_tree_root_role(pilot):
    t = pilot.tree()
    assert t["role"] in ("application", "plugin")

def test_param_roundtrip(pilot):
    pilot.set("PARAM_ID", 0.5)
    assert abs(pilot.get("PARAM_ID") - 0.5) < 1e-4

def test_unknown_param_returns_error(pilot):
    r = pilot.cmd(cmd="param_get", id="nonexistent_xyz")
    assert not r["ok"]
    assert "error" in r
```

---

## Checklist de validation

- [ ] Dispatcher : zéro appel UI/render, zéro panic, erreurs retournées proprement
- [ ] Arbre sémantique : lecture pure, `"role"` présent à la racine
- [ ] `param_set → param_get` : roundtrip cohérent
- [ ] Transport : thread séparé, non-bloquant sur le thread principal
- [ ] Drain : depuis le thread propriétaire de l'état (avant le rendu)
- [ ] Zéro allocation dans le hot path audio si applicable

---

## Références

- Arborescence conventionnelle : regrouper transport, dispatcher et arbre
  sémantique dans un module `ai_rpc/` à la racine des sources de l'application.
- Documenter le choix de transport dans un ADR (`docs/adr/`) : c'est une
  décision structurante, difficile à inverser une fois des clients écrits.
