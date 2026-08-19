(function () {
  const storageKey = document.body.dataset.scrollKey || "ax-return-scroll";

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if ((form.method || "get").toLowerCase() !== "post") return;

    if (!form.querySelector('input[name="next"]')) {
      const nextInput = document.createElement("input");
      nextInput.type = "hidden";
      nextInput.name = "next";
      nextInput.value = window.location.pathname + window.location.search + window.location.hash;
      form.appendChild(nextInput);
    }

    if (form.dataset.submitting === "1") {
      event.preventDefault();
      return;
    }
    if (!form.checkValidity()) return;

    try {
      sessionStorage.setItem(storageKey, JSON.stringify({
        path: window.location.pathname + window.location.search,
        y: window.scrollY,
        at: Date.now()
      }));
    } catch (error) {}

    form.dataset.submitting = "1";
    window.setTimeout(() => {
      form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(button => {
        button.disabled = true;
      });
    }, 0);
  });

  window.addEventListener("DOMContentLoaded", function () {
    restoreScrollPosition();
    initMobileNavigation();
  });

  function restoreScrollPosition() {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (!raw) return;

      sessionStorage.removeItem(storageKey);
      const state = JSON.parse(raw);
      const samePage = state.path === window.location.pathname + window.location.search;
      const recent = Date.now() - state.at < 15000;

      if (samePage && recent && Number.isFinite(state.y)) {
        window.setTimeout(() => window.scrollTo({ top: state.y, left: 0, behavior: "instant" }), 0);
      }
    } catch (error) {}
  }

  function initMobileNavigation() {
    const toggle = document.querySelector(".mobile-nav-toggle");
    const overlay = document.querySelector(".sidebar-overlay");
    const sidebar = document.querySelector(".sidebar");
    if (!toggle || !overlay || !sidebar) return;

    const setOpen = (open) => {
      document.body.classList.toggle("sidebar-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "메뉴 닫기" : "메뉴 열기");
    };

    toggle.addEventListener("click", () => setOpen(!document.body.classList.contains("sidebar-open")));
    overlay.addEventListener("click", () => setOpen(false));
    sidebar.querySelectorAll("a").forEach(link => link.addEventListener("click", () => setOpen(false)));
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") setOpen(false);
    });
  }
})();
