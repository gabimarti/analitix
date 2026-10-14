// Capturas ampliables: clic en una captura -> se abre grande sobre la página
// (elemento <dialog> nativo). Se cierra con un clic, con Esc o con el botón.
// Sin JavaScript las capturas se siguen viendo igual, solo sin ampliar.
(function () {
  var dialogo = document.createElement("dialog");
  dialogo.className = "zoom";
  dialogo.innerHTML =
    '<button type="button" class="zoom-close" aria-label="' +
    (document.documentElement.lang === "ca" ? "Tancar" : "Cerrar") +
    '">✕</button><img alt=""><p class="zoom-caption"></p>';
  document.body.appendChild(dialogo);
  var grande = dialogo.querySelector("img");
  var pie = dialogo.querySelector(".zoom-caption");

  document.querySelectorAll(".shots img").forEach(function (img) {
    img.tabIndex = 0;
    img.setAttribute("role", "button");
    function abrir() {
      grande.src = img.src;
      grande.alt = img.alt;
      var figcaption = img.closest("figure").querySelector("figcaption");
      pie.textContent = figcaption ? figcaption.textContent : "";
      dialogo.showModal();
    }
    img.addEventListener("click", abrir);
    img.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abrir(); }
    });
  });
  // Cualquier clic dentro del diálogo (imagen, fondo o botón) lo cierra.
  dialogo.addEventListener("click", function () { dialogo.close(); });
})();
