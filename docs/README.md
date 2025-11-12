# Signal Harvester Documentation

This directory contains the maintained documentation set for the Signal Harvester project.

For the canonical, up-to-date view of architecture, readiness status, and the prioritized roadmap, see:

- [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1)

For a single end-to-end project health check, from the `signal-harvester` directory run:

- `make verify-all` (see [`signal-harvester/Makefile`](signal-harvester/Makefile:7))

## 📚 Available Documentation

### For Users

- [USER_GUIDE.md](USER_GUIDE.md) - User-facing workflows and getting started
- [API.md](API.md) - API documentation and usage examples
- [API_EXAMPLES.md](API_EXAMPLES.md) - Practical API usage examples

### For Operators

- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide
- [OPERATIONS.md](OPERATIONS.md) - Day-to-day operations guide
- [BACKUP.md](BACKUP.md) - Backup and restore procedures

## 🚀 Quick Start

1. **Read the deployment guide** to get started:

   ```bash
   cat docs/DEPLOYMENT.md
   ```

2. **Check API documentation** for usage:

   ```bash
   cat docs/API.md
   ```

3. **Review operations guide** for maintenance:

   ```bash
   cat docs/OPERATIONS.md
   ```

## 📖 Documentation Status

This directory has evolved over time; some historical markers below may not reflect the current implementation. When in doubt, defer to [`signal-harvester/ARCHITECTURE_AND_READINESS.md`](signal-harvester/ARCHITECTURE_AND_READINESS.md:1) and validate via `make verify-all`.

- ✅ [`DEPLOYMENT.md`](DEPLOYMENT.md) - Deployment guide (maintained; aligns with canonical architecture).
- ✅ [`API.md`](API.md) - API reference (maintained; see canonical doc for overall system context).
- ✅ [`OPERATIONS.md`](OPERATIONS.md) - Operations runbook (maintained; aligns with canonical view).
- ✅ [`BACKUP.md`](BACKUP.md) - Backup and restore procedures (maintained).
- ✅ [`USER_GUIDE.md`](USER_GUIDE.md) - User-facing workflows (maintained).
- ℹ️ Other files in this directory not explicitly listed above MAY be historical; if they diverge from the canonical architecture/readiness, treat them as snapshots.

## 🤝 Contributing

When adding new features, please update the relevant documentation.

## 📞 Support

For issues and questions:

1. Check [OPERATIONS.md](OPERATIONS.md) for operational procedures
2. Review [API.md](API.md) documentation
3. Consult [ARCHITECTURE_AND_READINESS.md](../ARCHITECTURE_AND_READINESS.md) for system architecture
4. Open an issue on GitHub
