/**
 * Переключатель тем: Light / Dark / Coffee
 * Сохраняет выбор в localStorage.
 */
(function() {
    const STORAGE_KEY = 'sales-manager-theme';
    const DEFAULT_THEME = 'light';

    function getTheme() {
        return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
    }

    function setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem(STORAGE_KEY, theme);

        // Обновляем активную кнопку
        document.querySelectorAll('[data-theme-btn]').forEach(btn => {
            btn.classList.remove('ring-2', 'ring-offset-2');
            if (btn.dataset.themeBtn === theme) {
                btn.classList.add('ring-2', 'ring-offset-2');
            }
        });
    }

    // Применяем тему при загрузке
    document.addEventListener('DOMContentLoaded', function() {
        setTheme(getTheme());

        // Слушаем клики на кнопки тем
        document.querySelectorAll('[data-theme-btn]').forEach(btn => {
            btn.addEventListener('click', function() {
                setTheme(this.dataset.themeBtn);
            });
        });
    });

    // Применяем тему до рендера (предотвращает мигание)
    setTheme(getTheme());
})();
