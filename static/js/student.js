
document.addEventListener("DOMContentLoaded", () => {
  const desktop = document.querySelector(".ax-student-sidebar-toggle");
  const mobile = document.querySelector(".ax-student-mobile-toggle");

  if (desktop) {
    desktop.addEventListener("click", () => {
      document.body.classList.toggle("ax-student-sidebar-mini");
    });
  }

  if (mobile) {
    mobile.addEventListener("click", () => {
      document.body.classList.toggle("ax-student-sidebar-open");
    });
  }

  document.addEventListener("click", (event) => {
    if (window.innerWidth >= 992) return;
    if (!document.body.classList.contains("ax-student-sidebar-open")) return;
    const sidebar = document.querySelector(".ax-student-sidebar");
    if (sidebar && !sidebar.contains(event.target) && !mobile?.contains(event.target)) {
      document.body.classList.remove("ax-student-sidebar-open");
    }
  });
});
