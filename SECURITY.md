# Política de seguridad

Analitix trabaja con datos de salud, así que la seguridad y la privacidad
son una prioridad. Gracias por ayudar a mantenerla.

## Versiones con soporte

Solo la última versión publicada en
[Releases](https://github.com/gabimarti/analitix/releases) recibe
correcciones de seguridad.

## Cómo informar de una vulnerabilidad

**No abras una issue pública** para un problema de seguridad.

Usa el aviso privado de GitHub: pestaña **Security → Report a
vulnerability** de este repositorio
(<https://github.com/gabimarti/analitix/security/advisories/new>). Solo lo
verá el mantenedor.

Incluye, si puedes:

- qué versión usas (menú Ayuda → Acerca de) y cómo la instalaste
  (instalador o código fuente);
- los pasos para reproducir el problema y qué impacto tiene;
- cualquier dato de prueba necesario, **siempre ficticio**: nunca envíes
  informes, analíticas ni datos de salud reales (ver
  [CONTRIBUTING.md](CONTRIBUTING.md)).

Intentaré responder en un plazo de 7 días. Si se confirma el problema,
prepararé una corrección y una nueva versión, y te daré crédito en el
[registro de cambios](CHANGELOG.md) si lo deseas.

## Verificar el instalador

Cada [Release](https://github.com/gabimarti/analitix/releases) incluye
`SHA256SUMS.txt` con la huella del instalador. En Windows (PowerShell):

```text
Get-FileHash .\Analitix-Setup-X.Y.Z.exe -Algorithm SHA256
```

El resultado debe coincidir con el de `SHA256SUMS.txt`. Con
[GitHub CLI](https://cli.github.com/) también puedes comprobar que lo compiló
el workflow de este repositorio y no se subió a mano:

```text
gh attestation verify Analitix-Setup-X.Y.Z.exe --repo gabimarti/analitix
```

## Alcance

Analitix es una aplicación de escritorio que funciona en local: guarda los
datos cifrados (SQLCipher) en tu equipo y su única conexión a internet es la
comprobación opcional de versiones nuevas. Son especialmente relevantes los
problemas que puedan exponer esos datos: el cifrado de la base de datos, las
exportaciones, los registros de actividad o la lectura de PDF manipulados.
