@AGENTS.md

<!-- Las reglas del proyecto viven en AGENTS.md para que sirvan también a Codex/Cursor.
     Agrega aquí solo instrucciones específicas de Claude Code. -->

- Los hooks de `.claude/settings.json` corren ruff en cada archivo que editas y ruff + mypy + pytest
  cuando terminas tu turno. Si un hook reporta errores, corrígelos antes de dar la tarea por terminada.
- Para tareas que tocan varias capas o la autenticación, presenta primero un plan corto.
