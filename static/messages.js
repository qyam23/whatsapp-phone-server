(function () {
  "use strict";

  const clearButton = document.getElementById("clear-message-view");
  const tableBody = document.getElementById("messages-table-body");
  const clearedState = document.getElementById("messages-cleared-state");
  if (!clearButton || !tableBody || !clearedState) return;

  clearButton.addEventListener("click", function () {
    tableBody.replaceChildren();
    clearedState.hidden = false;
    clearButton.disabled = true;
  });
})();
