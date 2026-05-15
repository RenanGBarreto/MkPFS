# Environment variables

A short reference of environment variables that affect MkPFS CLI behavior.

| Variable | Type | Default | Description |
|---|---:|---|---|
| `MKPFS_NO_UTF8` | any | unset | When set (any value), CLI disables UTF-8 icons and uses ASCII fallback. Useful in CI or terminals without UTF-8 support. |

Set in shell:

```sh
export MKPFS_NO_UTF8=1
```

Keep this page short. See project docs or source for more details on logging and UI behavior.

