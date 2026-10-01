## Qué cambia y por qué

<!-- Breve descripción; enlaza la issue si existe (Closes #N). -->

## Comprobaciones

- [ ] `python -m pytest` pasa en local.
- [ ] Solo datos sintéticos: ningún PDF, nombre, DNI, NHC, fecha de nacimiento ni resultado real (ver CONTRIBUTING.md).
- [ ] Si cambia el comportamiento visible: `CHANGELOG.md` (`[Sin publicar]`) y documentación actualizados.
- [ ] Si toca el parser o un perfil `.toml`: probado con PDF reales del centro (en local, sin subirlos).
