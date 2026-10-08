# 局域网共享剪贴板（share_server）

局域网内共享剪贴板 + 文件协作工具。部署到任意一台机器后，同网段的电脑/手机/平板打开 `http://IP:8080/`，看到的是同一份内容，文字与文件实时同步。

- 纯 Python 标准库，**零第三方依赖**，单文件实现
- 跨平台：Windows / Linux / macOS / 树莓派 / Android（Termux）

## 功能

| 功能 | 说明 |
| --- | --- |
| 文字共享 | 任意设备保存文字，其他设备自动看到 |
| 文件上传/下载 | 多选或拖拽上传，点击下载 |
| 删除 | 单个删除或一键清空，**物理删除磁盘文件** |
| 上传预览 | 选中文件先进入「待上传」列表，点「上传」才入库 |
| 实时同步 | 所有页面约 2 秒自动刷新 |
| 并发安全 | 多人同时上传/删除/改文字不冲突 |

## 技术栈

- 后端：Python 3 标准库 `http.server`（多线程），无 Web 框架
- 存储：`manifest.json` 存文字与文件索引，文件本体存 `share_data/files/`
- 并发：`threading.Lock` + 临时文件原子替换
- 前端：原生 HTML / CSS / JS（`fetch`），无框架
- 同步：前端每 2 秒轮询 `/state`（不用 WebSocket，保持零依赖）
- 大文件：1MB 分块流式读写，不整体载入内存

## 目录结构

```
share_server.py   # 主程序（唯一需要运行的文件）
README.md
```

运行后自动生成数据目录（与 `share_server.py` **同一个目录**）：

```
share_data/
├── manifest.json   # 文字 + 文件索引
└── files/          # 上传的文件本体
```

例如 `share_server.py` 放在 `E:\莫移达\share_server_windows\`，数据就存在 `E:\莫移达\share_server_windows\share_data\`；Linux 同理，脚本放哪，数据就存哪。

## 快速开始

前置要求：装好 **Python 3**（建议 3.8+）。无需 nginx / MySQL / 宝塔，也无需 `pip install`。

```bash
python3 share_server.py          # Windows 上若报错，改用 python share_server.py
```

启动后：本机访问 `http://127.0.0.1:8080/`，其他设备访问 `http://本机IP:8080/`。

## 各平台部署

### Windows

1. 安装 Python：<https://www.python.org/downloads/> ，安装时**务必勾选 `Add Python to PATH`**。
2. 验证：`Win+R` → `cmd` → `python --version`。
3. 把 `share_server.py` 放到固定目录（如 `D:\share\`）后启动：

   ```bat
   D:
   cd D:\share
   python share_server.py
   ```

4. 查 IP：`ipconfig`，找「IPv4 地址」（形如 `192.168.x.x`）。
5. 放行防火墙：控制面板 → Windows Defender 防火墙 → 高级设置 → 入站规则 → 新建规则 → 端口 → TCP `8080` → 允许连接 → 保存。

其他设备用 `http://你的IP:8080/` 访问。

### Linux / 树莓派

```bash
python3 --version                 # 没有则：sudo apt update && sudo apt install -y python3
mkdir -p ~/share && cd ~/share    # 把 share_server.py 放进来
python3 share_server.py
hostname -I                       # 查 IP
sudo ufw allow 8080/tcp           # 有防火墙时放行
```

### macOS

```bash
python3 --version                         # 没有则：brew install python3
cd ~/share && python3 share_server.py     # 先放入 share_server.py
ipconfig getifaddr en0                    # 查 IP
```

首次运行若提示是否允许 Python 接受入站连接，选「允许」。

### Android（Termux）

```bash
pkg update && pkg upgrade -y
pkg install -y python openssh
nano share_server.py              # 粘贴代码，Ctrl+O 保存、Ctrl+X 退出
python3 share_server.py
ip addr show wlan0                # 找 inet 后的 192.168.x.x
```

可选远程管理：`passwd` 设密码、`sshd` 启动（监听 8022），电脑上 `ssh -p 8022 用户名@手机IP`。

## 开机自启动

**Windows（任务计划程序）**：`Win+R` → `taskschd.msc` → 创建基本任务 → 触发器「计算机启动时」→ 操作「启动程序」：程序填 `python.exe` 路径（`where python` 查）、参数填 `share_server.py` 路径、起始于脚本所在目录。

**Linux / macOS（systemd）**：新建 `/etc/systemd/system/share.service`：

```ini
[Unit]
Description=LAN Share Board
After=network.target

[Service]
Type=simple
User=你的用户名
ExecStart=/usr/bin/python3 /home/你的用户名/share/share_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now share
```

**临时后台运行**：`nohup python3 share_server.py > /dev/null 2>&1 &`

**Android（Termux:Boot）**：从 F-Droid 安装 `Termux:Boot`，新建 `~/.termux/boot/start-share.sh`：

```sh
#!/data/data/com.termux/files/usr/bin/sh
cd ~
exec python3 share_server.py
```

```bash
chmod +x ~/.termux/boot/start-share.sh
```

## 配置

改 `share_server.py` 顶部变量，改完重启服务：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PORT` | `8080` | 监听端口 |
| `MAX_TEXT` | 200MB | 单次文字上限 |
| `MAX_FILE` | 200MB | 单个文件上限 |
| `CHUNK` | 1MB | 分块读写大小 |
| `HERE` | 脚本同目录 | 数据存储根目录 |

## 使用说明

页面分三块：**文字**（输入后点「上传」保存）、**文件**（选择/拖拽文件 → 进入「待上传」列表 → 点「上传」入库，也可「清除选中」）、**文件列表**（单个下载或删除，删除为物理删除、不可恢复）。

## HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 前端页面 |
| `GET` | `/state` | 当前全部内容 JSON |
| `POST` | `/text` | 保存文字（body 为文字） |
| `POST` | `/upload?name=文件名` | 上传文件（body 为内容） |
| `GET` | `/file/<id>` | 下载文件 |
| `POST` | `/delete/<id>` | 删除文件 |
| `POST` | `/clear_files` | 清空文件 |

## 常见问题

- **别的设备打不开**：确认服务在运行、在同一局域网、Windows 已放行 8080、IP 填的是运行服务那台机器的。
- **8080 被占用**：改 `PORT` 后重启。
- **能绑 80 端口吗**：Linux/macOS 需 root（`sudo python3 share_server.py`），建议直接用 8080。
- **文件占空间吗**：存在 `share_data/files/`，会占磁盘；删除即物理删除。
- **支持文件夹上传吗**：暂不支持，当前为平铺文件列表。
- **多人同时用会乱吗**：不会，后端有全局锁保证一致性。

## 安全

无账号密码，内网可访问者均可增删内容，请只在可信局域网使用，勿暴露到公网。