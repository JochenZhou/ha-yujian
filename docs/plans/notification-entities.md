# Notification entities implementation plan

> For Hermes: execute using subagent-driven-development, review spec then quality. User authorized implementation; no additional approval required. Do not commit/push/release.

Goal: expose notification device controls and state as native HA entities; keep sending via services and add device configuration_url for the existing App WebUI. No music, drafts or custom frontend.

Architecture: shared per-entry client/coordinator and shared entity DeviceInfo retaining existing notify identity. Configuration writes merge actual echoed state; sending and dismiss refresh status. Poll health/history only; optional history failure must not erase a valid count as zero. Setup while offline must recover through polling. Existing notify IDs, options and mDNS discovery confirmation remain compatible.

Tech: Python, aiohttp, HA entity platforms, voluptuous, translated selectors.

## Task 1: protocol/service updates
Files: const.py, client.py, __init__.py, notify.py, services.yaml.
Add nine canonical theme IDs from App v1.9.0: xiuxian/default/palace/cyberpunk/wukong/matrix/ink_light/gamer/minecraft. Add per-notification theme across complete call chain. Allow title-only/media-only notifications while reject truly empty calls. Preserve speak off/ha/tv and boolean aliases. Keep entity/device/area service targeting, existing broadcast default. Do not turn a nonmatching explicit target into broadcast. Report request failure to caller rather than claim success; connection recovery only on network failure (not parameter/auth status). Include field selectors/translations. No Sendspin calls.
Verification: meaningful request tests capturing actual HTTP payload and service dispatch targeting, body ok:false, error classification, old call compatibility.

## Task 2: native entities and device visit link
Files: entity.py (shared), switch.py, select.py, button.py, binary_sensor.py, sensor.py, coordinator.py, notify.py, config_flow.py if needed.
One switch notification mute (sound/TTS only), selects global theme/default six positions, buttons dismiss and refresh, binary_sensor banner showing, sensors most recent notification (timestamp state with text/title/level/position attributes), history count, diagnostic service uptime seconds. App version in dynamic DeviceInfo. Retain notify unique_id and device identifier (current host based). Device configuration_url uses current host/port/token at /{token}/ui. Discovery address/token updates must refresh client and registry link; avoid token in entity attributes or diagnostics. Read health/history; no ADB side effects on refresh. Poll failure makes unavailable and recovers when device returns. Writes verify actual state. No history editor, replay, draft, media_player, music entities, custom frontend.
Verification: realistic HA runtime against two local mock App servers; list entities/registry, control readback, service targets, WebUI URL, offline recovery and rediscovery update. Restore test environment and mock settings afterward.

## Task 3: docs/translations and regression
Files: strings.json, translations/en.json, translations/zh-Hans.json, icons.json, README.md, tests/.
Translate entities, options, themes, service fields; strings and en identical. Correct mute semantics and has_media key. Explain native device visit link LAN requirement and nine themes, service examples, no music scope. Version 1.4.0 in manifest for local artifact (no tag/release). Add meaningful HA-backed tests if dependencies available, pure payload tests otherwise plus actual live integration validation by parent.
Run compileall, scripts/check_names.py, lint where available, tests and diff --check. Review spec then code quality. No production changes, no commit/push.
