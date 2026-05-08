# Euro_QA systemd deployment

This directory contains repo-versioned systemd unit files for running Euro_QA on a Linux host without tying the application lifecycle to an SSH session.

## Defaults

- Project path: `/home/root251/euroqa`
- Service user/group: `root251:root251`
- Backend: FastAPI via `uvicorn` on `0.0.0.0:8080` without reload
- Frontend: Vite preview on `0.0.0.0:4173` with `pnpm build` enforced before start
- Search dependencies: Docker Compose services `milvus-etcd`, `milvus-minio`, `milvus`, and `elasticsearch`
- Restart policy: all three units use `Restart=on-failure`
- The service files include a PATH that covers common user-level installs for `uv` and `pnpm`; adjust it if your tools live elsewhere

If the deployment user or project path differs, replace every `User=`, `Group=`, `WorkingDirectory=`, `Documentation=`, and user-home `PATH` fragment in `deploy/systemd/*.service` before installing the units. For example:

```bash
sed -i 's/User=root251/User=YOUR_USER/g; s/Group=root251/Group=YOUR_GROUP/g; s#/home/root251/euroqa#/home/YOUR_USER/euroqa#g; s#Documentation=file:/home/root251/euroqa/deploy/systemd/README.md#Documentation=file:/home/YOUR_USER/euroqa/deploy/systemd/README.md#g; s#/home/root251/.local#/home/YOUR_USER/.local#g' deploy/systemd/*.service
```

Review the edited files before copying them into systemd.

## Prepare the host

Run these commands on the target server after the repository is available at `/home/root251/euroqa`:

```bash
cd /home/root251/euroqa
uv sync
cd frontend
pnpm install
pnpm build
cd ..
docker compose pull milvus-etcd milvus-minio milvus elasticsearch
```

The backend reads configuration from the repository root `.env`, so make sure `/home/root251/euroqa/.env` is present before starting `euroqa-backend.service`.

## Install or update units

```bash
cd /home/root251/euroqa
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable euroqa-search-stack.service euroqa-backend.service euroqa-frontend.service
```

## Start

```bash
sudo systemctl start euroqa-search-stack.service
sudo systemctl start euroqa-backend.service
sudo systemctl start euroqa-frontend.service
```

The services are ordered so the backend requires `euroqa-search-stack.service`, and the frontend starts after the backend when systemd starts all enabled units.

## Stop

```bash
sudo systemctl stop euroqa-frontend.service
sudo systemctl stop euroqa-backend.service
sudo systemctl stop euroqa-search-stack.service
```

`euroqa-search-stack.service` runs `docker compose up` in the foreground so systemd can monitor the Compose process and apply `Restart=on-failure`. Its `ExecStop` uses `docker compose stop`, preserving container state and volumes.

## Restart after changes

The frontend unit runs `pnpm build` before each preview start. If you want to inspect the build manually first, run:

```bash
cd /home/root251/euroqa/frontend
pnpm build
sudo systemctl restart euroqa-frontend.service
```

Restart the backend after Python or environment changes:

```bash
cd /home/root251/euroqa
uv sync
sudo systemctl restart euroqa-backend.service
```

Restart the search stack after Docker Compose changes:

```bash
cd /home/root251/euroqa
sudo systemctl restart euroqa-search-stack.service
```

## Status

```bash
systemctl status euroqa-search-stack.service
systemctl status euroqa-backend.service
systemctl status euroqa-frontend.service
```

Port checks:

```bash
ss -ltnp | grep -E ':8080|:4173|:9200|:19530'
```

## Logs

```bash
journalctl -u euroqa-search-stack.service -f
journalctl -u euroqa-backend.service -f
journalctl -u euroqa-frontend.service -f
```

For recent boot logs without following:

```bash
journalctl -u euroqa-backend.service -b --no-pager
journalctl -u euroqa-frontend.service -b --no-pager
```

## Disable and rollback

To stop using the systemd units:

```bash
sudo systemctl disable --now euroqa-frontend.service euroqa-backend.service euroqa-search-stack.service
sudo rm -f /etc/systemd/system/euroqa-frontend.service
sudo rm -f /etc/systemd/system/euroqa-backend.service
sudo rm -f /etc/systemd/system/euroqa-search-stack.service
sudo systemctl daemon-reload
sudo systemctl reset-failed euroqa-frontend.service euroqa-backend.service euroqa-search-stack.service
```

To roll back to a previous repo version, check out the previous commit or release, reinstall the unit files from that version, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart euroqa-search-stack.service euroqa-backend.service euroqa-frontend.service
```

If only frontend assets changed, rebuild before restarting the frontend:

```bash
cd /home/root251/euroqa/frontend
pnpm build
sudo systemctl restart euroqa-frontend.service
```
