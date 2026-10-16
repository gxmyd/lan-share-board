#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
局域网共享剪贴板 / 文件协作服务
- 所有人访问 http://IP:8080/ 看到同一份内容
- 支持文字与多文件，均可自由增删改查
- 客户端自动刷新（轮询）实时同步，多用户并发安全
仅依赖 Python 标准库，零第三方依赖。
"""
import os
import sys
import json
import time
import secrets
import socket
import threading
import ipaddress
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))   # 数据存放到脚本所在目录，同目录部署（Windows/Linux 通用）
BASE = os.path.join(HERE, 'share_data')
FILE_DIR = os.path.join(BASE, 'files')
MANIFEST = os.path.join(BASE, 'manifest.json')
PORT = 8080
MAX_TEXT = 200 * 1024 * 1024          # 文字单次上限 200MB（避免一次吃满内存）
MAX_FILE = 2048 * 1024 * 1024          # 单个文件上限 2GB
CHUNK = 1024 * 1024                   # 分块读写 1MB

os.makedirs(FILE_DIR, exist_ok=True)

_lock = threading.Lock()


def load_state():
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict):
                d.setdefault('text', '')
                d.setdefault('files', [])
                return d
        except Exception:
            pass
    return {'text': '', 'files': []}


def save_state(state):
    tmp = MANIFEST + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, MANIFEST)


def cleanup_orphans():
    state = load_state()
    ids = {f.get('id') for f in state.get('files', [])}
    try:
        names = os.listdir(FILE_DIR)
    except Exception:
        return
    for fn in names:
        if fn not in ids:
            try:
                os.remove(os.path.join(FILE_DIR, fn))
            except Exception:
                pass


INDEX = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>共享剪贴板</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='22' fill='%234f46e5'/%3E%3Ctext x='50' y='70' font-size='52' text-anchor='middle' fill='%23ffffff' font-family='sans-serif'%3E%E5%89%AA%3C/text%3E%3C/svg%3E">
<style>
:root {
  --bg: #f4f5f7;
  --card: #ffffff;
  --border: #e6e8ec;
  --text: #1f2430;
  --muted: #8a919e;
  --primary: #4f46e5;
  --primary-h: #4338ca;
  --danger: #e11d48;
  --danger-h: #be123c;
  --radius: 14px;
  --shadow: 0 1px 2px rgba(16,24,40,.04), 0 4px 16px rgba(16,24,40,.06);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", Roboto, sans-serif; -webkit-font-smoothing: antialiased; }
.wrap { max-width: 720px; margin: 0 auto; padding: 28px 18px 60px; }

header { display: flex; align-items: flex-end; justify-content: space-between;
  margin-bottom: 20px; gap: 12px; flex-wrap: wrap; }
.brand h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -.3px; }
.brand .sub { margin: 4px 0 0; font-size: 13px; color: var(--muted); }
.hdr-right { display: flex; align-items: center; gap: 10px; }
.status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e;
  box-shadow: 0 0 0 3px rgba(34,197,94,.15); }
.dot.off { background: #ef4444; box-shadow: 0 0 0 3px rgba(239,68,68,.15); }

.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 20px; margin-bottom: 16px; }
.card-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 14px; }
.card-head h2 { margin: 0; font-size: 15px; font-weight: 600; }
.card-head .hint { font-size: 12px; color: var(--muted); }

textarea { width: 100%; min-height: 150px; padding: 13px 14px; border: 1px solid var(--border);
  border-radius: 10px; font-size: 14px; line-height: 1.6; resize: vertical;
  font-family: inherit; color: var(--text); background: #fbfbfd; transition: border-color .15s, box-shadow .15s; }
textarea:focus { outline: none; border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(79,70,229,.12); background: #fff; }

.drop { display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 6px; padding: 26px 16px; border: 1.5px dashed #c9cdd6; border-radius: 12px;
  cursor: pointer; background: #fbfbfd; transition: border-color .15s, background .15s; }
.drop:hover, .drop.over { border-color: var(--primary); background: #f5f4ff; }
.drop input { display: none; }
.drop .plus { font-size: 26px; color: #b9bec9; line-height: 1; }
.drop .txt { font-size: 13px; color: var(--muted); }

.actions { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
.btn { border: none; border-radius: 9px; padding: 9px 18px; font-size: 14px; font-weight: 500;
  cursor: pointer; transition: background .15s, transform .05s; font-family: inherit; }
.btn:active { transform: translateY(1px); }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.btn.primary { background: var(--primary); color: #fff; }
.btn.primary:hover { background: var(--primary-h); }
.btn.danger { background: var(--danger); color: #fff; }
.btn.danger:hover { background: var(--danger-h); }
.btn.ghost { background: #fff; color: var(--text); border: 1px solid var(--border); }
.btn.ghost:hover { background: #f4f5f7; }
.btn.sm { padding: 6px 12px; font-size: 13px; }

.pending-files { margin-top: 12px; border-top: 1px dashed var(--border); }
.pending-files:empty { display: none; }
.pending-title { font-size: 12px; color: var(--muted); padding: 12px 4px 4px; }

#filelist { display: flex; flex-direction: column; }
.frow { display: flex; align-items: center; gap: 12px; padding: 11px 4px;
  border-bottom: 1px solid var(--border); }
.frow:last-child { border-bottom: none; }
.f-ico { flex: none; width: 34px; height: 34px; border-radius: 8px; background: #eef2ff;
  display: flex; align-items: center; justify-content: center; color: var(--primary); }
.f-info { flex: 1; min-width: 0; }
.f-name { font-size: 14px; font-weight: 500; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.f-meta { font-size: 12px; color: var(--muted); margin-top: 2px; }
.empty { padding: 22px 0; text-align: center; color: var(--muted); font-size: 13px; }

#toast { position: fixed; left: 50%; bottom: 30px; transform: translateX(-50%) translateY(10px);
  background: rgba(17,24,39,.92); color: #fff; padding: 9px 18px; border-radius: 20px;
  font-size: 13px; opacity: 0; pointer-events: none; transition: opacity .2s, transform .2s; }
#toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <h1>共享剪贴板</h1>
      <p class="sub">同一局域网内，所有人看到同一份内容，可自由增删改查</p>
    </div>
    <div class="hdr-right">
      <div class="status"><span class="dot" id="dot"></span><span id="dotLabel">已连接</span></div>
      <button class="btn ghost" id="btnRefresh" onclick="refresh(true)">刷新</button>
    </div>
  </header>

  <section class="card">
    <div class="card-head"><h2>文字</h2><span class="hint">输入后点「上传」保存</span></div>
    <textarea id="text" placeholder="写下要共享的文字…"></textarea>
    <div class="actions">
      <button class="btn primary" id="btnText" onclick="uploadText()">上传</button>
      <button class="btn danger" onclick="clearText()">清除文字</button>
    </div>
  </section>

  <section class="card">
    <div class="card-head"><h2>文件</h2><span class="hint">支持多选，也可拖拽到这里</span></div>
    <label class="drop" id="drop">
      <input type="file" id="file" multiple>
      <span class="plus">＋</span>
      <span class="txt">点击选择文件，或拖拽文件到此处</span>
    </label>
    <div id="pendingFiles" class="pending-files"></div>
    <div class="actions">
      <button class="btn primary" id="btnFile" onclick="uploadFiles()">上传</button>
      <button class="btn danger" onclick="clearFiles()">清除全部文件</button>
    </div>
  </section>

  <section class="card">
    <div class="card-head"><h2>文件列表</h2><span class="hint" id="fileCount">0 个文件</span></div>
    <div id="filelist"><div class="empty">暂无文件</div></div>
  </section>
</div>
<div id="toast"></div>

<script>
var POLL_MS = 2000;
var textBox = document.getElementById('text');

function esc(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function fmtSize(n) {
  if (n == null) return '';
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n/1024).toFixed(1) + ' KB';
  if (n < 1073741824) return (n/1048576).toFixed(1) + ' MB';
  return (n/1073741824).toFixed(1) + ' GB';
}
function fmtTime(t) {
  var d = new Date(t * 1000);
  function p(x) { return x < 10 ? '0' + x : '' + x; }
  return (d.getMonth()+1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}
function toast(msg) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'show';
  clearTimeout(t._t);
  t._t = setTimeout(function () { t.className = ''; }, 2000);
}
function setStatus(ok) {
  var d = document.getElementById('dot');
  var l = document.getElementById('dotLabel');
  d.className = ok ? 'dot' : 'dot off';
  l.textContent = ok ? '已连接' : '未连接';
}
function renderFiles(files) {
  var box = document.getElementById('filelist');
  var cnt = document.getElementById('fileCount');
  cnt.textContent = (files ? files.length : 0) + ' 个文件';
  if (!files || !files.length) { box.innerHTML = '<div class="empty">暂无文件</div>'; return; }
  var html = '';
  files.forEach(function (f) {
    html += '<div class="frow">' +
      '<span class="f-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg></span>' +
      '<div class="f-info"><div class="f-name">' + esc(f.name) + '</div>' +
      '<div class="f-meta">' + fmtSize(f.size) + ' · ' + fmtTime(f.time) + '</div></div>' +
      '<a class="btn ghost sm" href="/file/' + encodeURIComponent(f.id) + '" target="_blank">下载</a>' +
      '<button class="btn danger sm" data-del="' + f.id + '">删除</button>' +
      '</div>';
  });
  box.innerHTML = html;
}
var lastText = '';      // 最近一次与服务器一致的文字
var textDirty = false;  // 是否有未保存的文字改动

function setTextBox(t) {
  textBox.value = t;
  lastText = t;
  textDirty = false;
}
textBox.addEventListener('input', function () {
  textDirty = (textBox.value !== lastText);
});
async function refresh(force) {
  try {
    var r = await fetch('/state', { cache: 'no-store' });
    var s = await r.json();
    setStatus(true);
    // 有未保存改动时跳过文字更新，保护用户输入；手动刷新/上传后恢复自动刷新
    if (force || !textDirty) setTextBox(s.text || '');
    renderFiles(s.files || []);
  } catch (e) { setStatus(false); }
}
async function uploadText() {
  var t = textBox.value;
  var btn = document.getElementById('btnText');
  btn.disabled = true;
  btn.textContent = '上传中…';
  try {
    var r = await fetch('/text', { method: 'POST', body: t });
    var j = await r.json();
    if (j.ok) { setTextBox(t); toast('文字已上传'); refresh(); } else { toast('失败：' + (j.error || '未知')); }
  } catch (e) { toast('请求失败：' + e); }
  btn.disabled = false;
  btn.textContent = '上传';
}
async function clearText() {
  if (!confirm('确定清除全部文字内容？')) return;
  try {
    await fetch('/clear_text', { method: 'POST' });
    setTextBox('');
    toast('文字已清除'); refresh();
  } catch (e) { toast('失败：' + e); }
}
async function uploadFileList(files) {
  var arr = Array.from(files || []);
  if (!arr.length) return 0;
  var btn = document.getElementById('btnFile');
  btn.disabled = true;
  btn.textContent = '上传中…';
  var ok = 0;
  for (var i = 0; i < arr.length; i++) {
    var f = arr[i];
    try {
      var r = await fetch('/upload?name=' + encodeURIComponent(f.name), { method: 'POST', body: f });
      var j = await r.json();
      if (j.ok) ok++; else toast('「' + f.name + '」失败：' + (j.error || '未知'));
    } catch (e) { toast('「' + f.name + '」失败：' + e); }
  }
  btn.disabled = false;
  btn.textContent = '上传';
  toast('已上传 ' + ok + ' 个文件');
  refresh();
  return ok;
}
// 待上传文件队列：选中后先预览，点击「上传」才真正提交
var pendingFiles = [];
function renderPendingFiles() {
  var box = document.getElementById('pendingFiles');
  if (!pendingFiles.length) { box.innerHTML = ''; return; }
  var html = '<div class="pending-title">待上传文件（' + pendingFiles.length + '）</div>';
  pendingFiles.forEach(function (f, idx) {
    html += '<div class="frow">' +
      '<span class="f-ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg></span>' +
      '<div class="f-info"><div class="f-name">' + esc(f.name) + '</div>' +
      '<div class="f-meta">' + fmtSize(f.size) + '</div></div>' +
      '<button class="btn danger sm" data-pending="' + idx + '">移除</button>' +
      '</div>';
  });
  box.innerHTML = html;
}
document.getElementById('file').addEventListener('change', function (e) {
  var files = Array.from(e.target.files);
  if (files.length) {
    pendingFiles = pendingFiles.concat(files);
    renderPendingFiles();
    e.target.value = '';
  }
});
document.getElementById('pendingFiles').addEventListener('click', function (e) {
  var el = e.target && e.target.closest ? e.target.closest('[data-pending]') : null;
  if (el) {
    pendingFiles.splice(parseInt(el.getAttribute('data-pending'), 10), 1);
    renderPendingFiles();
  }
});
function clearPendingFiles() {
  pendingFiles = [];
  renderPendingFiles();
}
async function uploadFiles() {
  if (!pendingFiles.length) { toast('请先选择文件'); return; }
  await uploadFileList(pendingFiles);
  pendingFiles = [];
  renderPendingFiles();
}
async function delFile(id) {
  if (!confirm('确定删除该文件？')) return;
  try {
    await fetch('/delete/' + encodeURIComponent(id), { method: 'POST' });
    toast('已删除'); refresh();
  } catch (e) { toast('失败：' + e); }
}
async function clearFiles() {
  if (!confirm('确定清除全部文件？')) return;
  try {
    await fetch('/clear_files', { method: 'POST' });
    toast('全部文件已清除'); refresh();
  } catch (e) { toast('失败：' + e); }
}

// 拖拽上传
var drop = document.getElementById('drop');
['dragenter', 'dragover'].forEach(function (ev) {
  drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); });
});
['dragleave', 'drop'].forEach(function (ev) {
  drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('over'); });
});
drop.addEventListener('drop', function (e) {
  var files = e.dataTransfer && e.dataTransfer.files;
  if (files && files.length) uploadFileList(Array.from(files));
});

document.getElementById('filelist').addEventListener('click', function (e) {
  var el = e.target && e.target.closest ? e.target.closest('[data-del]') : null;
  if (el) delFile(el.getAttribute('data-del'));
});

refresh();
setInterval(refresh, POLL_MS);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = 'ShareServer/2.1'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype='text/html; charset=utf-8', extra=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _send_json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False), 'application/json; charset=utf-8')

    def _content_length(self):
        try:
            return int(self.headers.get('Content-Length', '0'))
        except Exception:
            return 0

    def _read_body(self, limit):
        length = self._content_length()
        if length <= 0:
            return b''
        if length > limit:
            return None
        return self.rfile.read(length)

    @staticmethod
    def _cd(filename):
        ascii_name = filename.encode('ascii', 'ignore').decode('ascii') or 'file'
        encoded = urllib.parse.quote(filename)
        return ("attachment; filename=\"" + ascii_name + "\"; "
                + "filename*=UTF-8''" + encoded)

    def do_HEAD(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ('/', '/index.html'):
            body, ctype = INDEX, 'text/html; charset=utf-8'
        elif path == '/state':
            body, ctype = json.dumps(self._load(), ensure_ascii=False), 'application/json; charset=utf-8'
        else:
            body, ctype = '', 'text/html; charset=utf-8'
        n = len(body.encode('utf-8'))
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(n))
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ('/', '/index.html'):
            self._send(200, INDEX)
        elif path == '/favicon.ico':
            self._send(204, b'')
        elif path == '/state':
            self._send_json(self._load())
        elif path.startswith('/file/'):
            self._download(path[len('/file/'):])
        else:
            self._send(404, '<h1>404</h1><p>页面不存在</p>')

    def _load(self):
        with _lock:
            return load_state()

    def _download(self, fid):
        if not fid or '/' in fid:
            self._send(404, '<h1>404</h1>')
            return
        with _lock:
            state = load_state()
            name = fid
            for f in state.get('files', []):
                if f.get('id') == fid:
                    name = f.get('name', fid)
                    break
        fp = os.path.join(FILE_DIR, fid)
        try:
            size = os.path.getsize(fp)
        except OSError:
            self._send(404, '<h1>404</h1><p>文件不存在或已删除</p>')
            return
        try:
            fh = open(fp, 'rb')
        except Exception:
            self._send(404, '<h1>404</h1>')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(size))
        self.send_header('Content-Disposition', self._cd(name))
        self.end_headers()
        try:
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except Exception:
            pass
        finally:
            fh.close()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/text':
            self._set_text()
        elif path == '/clear_text':
            self._clear_text()
        elif path == '/clear_files':
            self._clear_files()
        elif path == '/upload':
            self._upload()
        elif path.startswith('/delete/'):
            self._delete(path[len('/delete/'):])
        else:
            self._send(404, '<h1>404</h1>')

    def _set_text(self):
        data = self._read_body(MAX_TEXT)
        if data is None:
            self._send_json({'ok': False, 'error': '内容过大'})
            return
        text = data.decode('utf-8', 'replace')
        with _lock:
            state = load_state()
            state['text'] = text
            save_state(state)
        self._send_json({'ok': True})

    def _clear_text(self):
        with _lock:
            state = load_state()
            state['text'] = ''
            save_state(state)
        self._send_json({'ok': True})

    def _clear_files(self):
        with _lock:
            state = load_state()
            for f in state.get('files', []):
                fid = f.get('id', '')
                fp = os.path.join(FILE_DIR, fid)
                if fid and os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
            state['files'] = []
            save_state(state)
        self._send_json({'ok': True})

    def _upload(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        name = qs.get('name', ['file'])[0]
        length = self._content_length()
        if length <= 0:
            self._send_json({'ok': False, 'error': '空文件'})
            return
        if length > MAX_FILE:
            self._send_json({'ok': False, 'error': '文件超过 200MB 限制'})
            return
        fid = secrets.token_urlsafe(9)
        fp = os.path.join(FILE_DIR, fid)
        # 分块写入磁盘，不整体读入内存，避免大文件撑爆内存
        written = 0
        try:
            with open(fp, 'wb') as fh:
                while written < length:
                    chunk = self.rfile.read(min(CHUNK, length - written))
                    if not chunk:
                        break
                    fh.write(chunk)
                    written += len(chunk)
        except Exception:
            written = -1
        if written != length:
            try:
                os.remove(fp)
            except Exception:
                pass
            self._send_json({'ok': False, 'error': '写入失败'})
            return
        with _lock:
            state = load_state()
            state.setdefault('files', []).append({
                'id': fid, 'name': name, 'size': length, 'time': int(time.time()),
            })
            save_state(state)
        self._send_json({'ok': True, 'id': fid, 'name': name, 'size': length})

    def _delete(self, fid):
        if not fid or '/' in fid:
            self._send_json({'ok': False, 'error': '非法文件'})
            return
        with _lock:
            state = load_state()
            state['files'] = [f for f in state.get('files', []) if f.get('id') != fid]
            save_state(state)
            fp = os.path.join(FILE_DIR, fid)
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass
        self._send_json({'ok': True})


class Server(ThreadingHTTPServer):
    request_queue_size = 128


def list_local_ips():
    """收集本机所有 IPv4，192.168.* 排最前，过滤 loopback/link-local"""
    ips = set()
    try:
        hn = socket.gethostname()
        for info in socket.getaddrinfo(hn, None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    valid = []
    for ip in ips:
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_loopback or addr.is_link_local or addr.is_multicast:
                continue
            valid.append(ip)
        except ValueError:
            continue
    valid.sort(key=lambda x: (0 if x.startswith('192.168.') else 1 if ipaddress.ip_address(x).is_private else 2, x))
    return valid


if __name__ == '__main__':
    cleanup_orphans()
    srv = Server(('0.0.0.0', PORT), Handler)
    print('ShareServer v2.1 已启动，监听 0.0.0.0:%d' % PORT, flush=True)
    ips = list_local_ips()
    port_suffix = ':%d' % PORT
    if ips:
        print('其他设备访问地址：', flush=True)
        for ip in ips:
            print('  http://%s%s/' % (ip, port_suffix), flush=True)
    else:
        print('  http://127.0.0.1%s/ （仅本机）' % port_suffix, flush=True)

    # Windows 双击运行后自动打开浏览器（用第一个 IP，即列表第一行）；其他平台跳过
    if sys.platform == 'win32':
        try:
            webbrowser.open('http://%s%s/' % (ips[0] if ips else '127.0.0.1', port_suffix))
        except Exception:
            pass

    srv.serve_forever()