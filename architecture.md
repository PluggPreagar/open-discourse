# Architektur

```mermaid
flowchart LR
  Browser -->|fetch NEXT_PUBLIC_PROXY_ENDPOINT| Proxy
  Proxy -->|pg pool, Port 5432| Database[(Postgres: next)]
  Python[python/build.sh] -->|Reden, Politiker, Fraktionen| Database
  Database -.->|yarn db:update:local\nDROP/CREATE next| Database

  subgraph Frontend[frontend :3000 - Next.js]
    Browser
  end
  subgraph Proxy[proxy :5300 - Express]
  end
  subgraph DB[database :5432 - Postgres+rum]
    Database
  end
```

- **frontend**: Next.js, holt Daten client-seitig direkt vom Proxy (kein SSR-Fetch).
- **proxy**: einzige Komponente mit DB-Zugriff, cached GET-Responses, rate-limited.
- **database**: Docker-Image ist nur der leere Postgres-Server; Schema/Daten kommen erst durch `yarn db:update:local` (legt `next` neu an) + `python/build.sh` (Pipeline-Upload).
