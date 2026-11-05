# BlogDrop sample

This sample runs BlogDrop as four containers: MySQL, the Node.js backend,
the static frontend, and an Nginx gateway.

From the repository root, start it with:

```powershell
vcontainer compose up "backend\samples\blogdrop\config.yaml"
```

Open `http://127.0.0.1:8080` after the services start.

The application directories use bind mounts relative to `config.yaml`. Keep
the `backend`, `database`, `frontend`, and `nginx` directories beside the
Compose file when copying this sample to another machine.

Stop the project without removing its containers:

```powershell
vcontainer compose stop "backend\samples\blogdrop\config.yaml"
```

Remove its containers while preserving the named database volume:

```powershell
vcontainer compose down "backend\samples\blogdrop\config.yaml"
```
