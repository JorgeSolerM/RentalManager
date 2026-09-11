"use strict";
document.getElementById("select-ready-properties")?.addEventListener("click", () => {
  document.querySelectorAll('#property-settlement-selection input[data-readiness="ready"]').forEach(input => {
    input.checked = true;
  });
});
