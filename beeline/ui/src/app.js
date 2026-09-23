/* Entry point for the data-connected UI. No business fixtures are bundled. */
import("./workspace.js").catch(() => {
  const main = document.querySelector("#main");
  main.textContent =
    "Не удалось загрузить интерфейс. Запустите python3 server.py и обновите страницу.";
  main.setAttribute("role", "alert");
});
