# Materials

These are starter references for Codex, not live configuration.

- `config/`: example application configuration and service manifests.
- `systemd/`: example unit files. Review paths, users, permissions and capabilities before installation.
- `sql/`: reference schema. Production schema should be managed through versioned migrations.
- `api/`: initial API surface outline.
- `ui/`: navigation and visual design guidance.
- `scripts/host_audit_readonly.sh`: read-only host inventory helper.

Do not copy placeholders into production without checking the real host. Never include secrets in Git or logs.
