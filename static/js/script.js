document.addEventListener("DOMContentLoaded", function () {
  var toggle = document.getElementById("sidebarToggle");
  var sidebar = document.querySelector(".sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
    document.addEventListener("click", function (e) {
      if (window.innerWidth <= 900 && sidebar.classList.contains("open")) {
        if (!sidebar.contains(e.target) && e.target !== toggle && !toggle.contains(e.target)) {
          sidebar.classList.remove("open");
        }
      }
    });
  }

  // Auto-dismiss flash messages after a few seconds
  document.querySelectorAll(".flash").forEach(function (flash) {
    setTimeout(function () {
      flash.style.transition = "opacity 0.4s ease";
      flash.style.opacity = "0";
      setTimeout(function () { flash.remove(); }, 400);
    }, 5000);
  });
});
