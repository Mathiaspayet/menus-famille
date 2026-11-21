// Bouton « Modifier avec Claude » quand un projet Claude est configuré :
// on copie le contexte (jour, repas prévus…) avant d'ouvrir le projet,
// puisqu'un lien de projet ne peut pas pré-remplir la question.
(function () {
  document.addEventListener("click", e => {
    const a = e.target.closest("a.claude[data-copier]");
    if (!a) return;
    const texte = a.dataset.copier;
    const aide = a.nextElementSibling && a.nextElementSibling.classList.contains("claude-aide") ? a.nextElementSibling : null;
    function copieSecours() {
      const t = document.createElement("textarea");
      t.value = texte; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
      document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); } catch (err) { /* rien */ }
      t.remove();
    }
    try {
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(texte).catch(copieSecours);
      else copieSecours();
    } catch (err) { copieSecours(); }
    if (aide) aide.hidden = false;
  });
})();
