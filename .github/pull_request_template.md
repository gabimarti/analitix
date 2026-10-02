## Qué cambia y por qué

<!-- Breve descripción; enlaza la issue si existe (Closes #N). -->

## Comprobaciones

- [ ] He leído la [política de contribuciones](https://github.com/gabimarti/analitix/blob/develop/docs/POLITICA_CONTRIBUCIONES.md) (seguridad, privacidad e integridad) y el cambio la cumple.
- [ ] `python -m pytest` pasa en local.
- [ ] Solo datos sintéticos: ningún PDF, nombre, DNI, NHC, fecha de nacimiento ni resultado real (ver CONTRIBUTING.md).
- [ ] Sin conexiones de red, dependencias ni registros (log) nuevos con datos personales; o, si los hay, acordados antes en una issue.
- [ ] Todo valor, fórmula o umbral clínico nuevo lleva su fuente verificable (DOI/PMID) y no se presenta como diagnóstico.
- [ ] Si cambia el comportamiento visible: `CHANGELOG.md` (`[Sin publicar]`) y documentación actualizados.
- [ ] Si toca el parser o un perfil `.toml`: probado con PDF reales del centro (en local, sin subirlos).
