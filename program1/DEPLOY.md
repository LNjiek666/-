# 上线部署指南

本文档说明如何把互动课堂答题系统部署到公网服务器，让学生和老师通过域名访问。

## 代码已完成的改造

- 学生端、教师端页面的 API 地址改为同源获取（`window.location.origin`），不再写死 `localhost`
- 教师端页面由后端 `/teacher` 路径托管（学生端仍为 `/`）
- 服务启动支持环境变量 `HOST` / `PORT` 覆盖

## 目标架构

```
学生/老师浏览器 -> https://你的域名
                        |
                     Nginx (80/443, HTTPS)
                        |
                127.0.0.1:8000 (uvicorn + FastAPI + SQLite)
```

## 一、准备阶段（本机）

1. 更换管理口令：`ADMIN_KEY` 默认是 `teacher888`，公网部署必须换成随机强口令（见第五步）。
2. 备份数据：`answer_records.db` 里是学生账号和全部答题记录，上线前先复制一份保存。
3. 清理演示数据（可选）：执行过 `seed_data.py` 的话，演示学生和答题记录会公网可见，建议清空。

## 二、购买服务器与域名

- 服务器：阿里云 / 腾讯云等轻量应用服务器，2 核 2G 即可，系统选 Ubuntu 22.04 或 Debian 12。
- 域名：注册一个域名（.com / .cn 均可）。
- 备案：服务器在大陆时，域名必须完成 ICP 备案（约 1~2 周）。赶时间可选香港节点（免备案，但国内访问稍慢）。

## 三、服务器初始化

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git
```

## 四、上传代码并安装依赖

```bash
sudo mkdir -p /opt/interactive-classroom
sudo chown $USER /opt/interactive-classroom
cd /opt/interactive-classroom
# 用 git 拉取，或用 SFTP / 宝塔面板把整个项目（含 answer_records.db）传到这里
git clone <你的仓库地址> .

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 五、配置管理口令

创建 `/opt/interactive-classroom/.env`：

```ini
ADMIN_KEY=换成你的强口令
```

systemd 服务会自动读取该文件（见下一步）。

## 六、注册 systemd 服务

```bash
cd /opt/interactive-classroom
sudo chown -R www-data:www-data /opt/interactive-classroom
sudo cp deploy/interactive-classroom.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now interactive-classroom
sudo systemctl status interactive-classroom
```

说明：服务只监听 `127.0.0.1:8000`，不直接暴露公网，外部访问统一走 Nginx。

## 七、配置 Nginx

```bash
cd /opt/interactive-classroom
# 先把 deploy/nginx.conf 里的 your-domain.com 换成你的域名
sudo cp deploy/nginx.conf /etc/nginx/sites-available/interactive-classroom
sudo ln -s /etc/nginx/sites-available/interactive-classroom /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 八、配置 HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名
```

证书自动续期由 certbot 自带的定时任务完成，无需手动处理。

## 九、域名解析

在域名服务商的控制台把 A 记录指向服务器公网 IP。生效后访问：

- 学生端：`https://你的域名/`
- 教师端：`https://你的域名/teacher`（操作名单时输入第五步设置的 `ADMIN_KEY`）

## 十、验证清单

- [ ] `https://你的域名/` 学生页面能正常打开并提交答题
- [ ] `https://你的域名/teacher` 教师看板能加载统计数据
- [ ] 用 `http://` 访问会自动跳转 `https://`
- [ ] 输入错误 `ADMIN_KEY` 无法管理名单

## 数据备份

SQLite 就是一个文件，每天定时打包即可。示例 cron（每天凌晨 3 点）：

```bash
3 3 * * * tar -czf /backup/ic-$(date +\%F).tar.gz -C /opt/interactive-classroom answer_records.db
```

## 日常更新代码

```bash
cd /opt/interactive-classroom
git pull
source .venv/bin/activate
pip install -r requirements.txt   # 依赖有变化时才需要
sudo systemctl restart interactive-classroom
```

## 常见问题

- **502 Bad Gateway**：后端没起来。`sudo systemctl status interactive-classroom` 查看状态和日志，确认 8000 端口在监听。
- **页面能开但提交失败**：确认访问的是 `https://你的域名/`，而不是本地保存的旧 HTML 文件。
- **域名解析了还打不开**：检查云服务器安全组 / 防火墙是否放行 80、443 端口。
- **并发量变大**：SQLite 适合百人级课堂场景；如果预期并发很高，把 `database.py` 换成 PostgreSQL 连接串即可。

## 安全提醒

- `ADMIN_KEY` 必须改为强口令，且 `.env` 不要提交进 git 仓库。
- 学生默认密码 `88888888` 太弱，建议上线后通过教师端名单管理统一重置。
- 系统没有开放注册，学生必须先在教师端上传名单才能答题，天然只对名单内学生开放。
