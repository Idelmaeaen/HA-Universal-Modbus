## Home Assistant brands submission

Target repository: `home-assistant/brands`

Target path for this integration:

```text
custom_integrations/universal_modbus/
```

Files to include:

```text
icon.png
icon@2x.png
logo.png
logo@2x.png
```

Source files in this repository:

```text
brand/icon.png
brand/icon@2x.png
brand/logo.png
brand/logo@2x.png
```

Validated image sizes:

- `icon.png`: `256x256`
- `icon@2x.png`: `512x512`
- `logo.png`: `828x256`
- `logo@2x.png`: `1657x512`

Notes:

- The directory name must match the integration domain from `custom_components/universal_modbus/manifest.json`.
- Local brand assets already exist under `custom_components/universal_modbus/brand/`, but HACS may still rely on the shared `brands` repository for its catalog icon.
