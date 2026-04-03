document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("input, select, textarea").forEach((element) => {
        if (!element.classList.contains("form-check-input")) {
            element.classList.add(element.tagName === "SELECT" ? "form-select" : "form-control");
        }
    });

    const themeStorageKey = "msedcl-theme";
    const themeToggleButton = document.querySelector("[data-theme-toggle]");
    const themeLabel = document.querySelector("[data-theme-label]");
    const root = document.documentElement;

    function applyTheme(theme) {
        const nextTheme = theme === "dark" ? "dark" : "light";
        root.setAttribute("data-theme", nextTheme);
        localStorage.setItem(themeStorageKey, nextTheme);
        if (themeLabel) {
            themeLabel.textContent = nextTheme === "dark" ? "Light mode" : "Dark mode";
        }
        if (themeToggleButton) {
            themeToggleButton.setAttribute("aria-label", `Switch to ${nextTheme === "dark" ? "light" : "dark"} mode`);
        }
    }

    if (themeToggleButton) {
        applyTheme(localStorage.getItem(themeStorageKey) || root.getAttribute("data-theme") || "light");
        themeToggleButton.addEventListener("click", () => {
            const currentTheme = root.getAttribute("data-theme") || "light";
            applyTheme(currentTheme === "dark" ? "light" : "dark");
        });
    }

    document.querySelectorAll("[data-visibility-checkbox-list]").forEach((container) => {
        container.classList.add("access-checkbox-list");
    });
});
