/**
 * Календарь отгрузок и задач менеджеров.
 *
 * Источники данных:
 *   GET /api/calendar-events          → события (отгрузки + задачи)
 *   GET /api/calendar-events/managers → легенда цветов менеджеров
 *   GET /api/employees                → список менеджеров для дропдаунов
 *
 * Функциональность:
 *   - Двухцветный бейдж для совместных задач (градиент 50/50)
 *   - Hover → яркость задачи
 *   - Клик на бейдж задачи → модальное окно управления
 *   - Клик на ячейку дня → панель деталей под календарём
 */
(function () {
    'use strict';

    const calendarEl = document.getElementById('shipment-calendar');
    if (!calendarEl) return;

    let currentDate  = new Date();
    let events       = [];
    let employees    = [];
    let selectedDate = null;

    const MONTH_NAMES = [
        'Январь','Февраль','Март','Апрель','Май','Июнь',
        'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
    ];
    const MONTH_GEN = [
        'января','февраля','марта','апреля','мая','июня',
        'июля','августа','сентября','октября','ноября','декабря',
    ];
    const PRIORITY_RU = { low:'Низкий', medium:'Средний', high:'Высокий', critical:'Критический' };
    const STATUS_RU   = {
        pending:'Ожидает', in_progress:'В работе', completed:'Выполнено',
        overdue:'Просрочено', new:'Новая', negotiation:'Переговоры',
        contract:'Контракт', won:'Выиграна', lost:'Проиграна', stale:'Заморожена',
    };

    // ── Загрузка данных ───────────────────────────────────────────────────────

    async function loadEvents() {
        try {
            const [evResp, mgResp, empResp] = await Promise.all([
                fetch('/api/calendar-events'),
                fetch('/api/calendar-events/managers'),
                fetch('/api/employees'),
            ]);
            events    = await evResp.json();
            employees = await empResp.json();
            renderLegend(await mgResp.json());
        } catch (e) {
            console.error('Ошибка загрузки данных календаря:', e);
        }
        renderCalendar();
    }

    // ── Легенда ───────────────────────────────────────────────────────────────

    function renderLegend(managers) {
        const el = document.getElementById('calendar-legend');
        if (!el || !managers || !managers.length) return;
        const badges = managers.map(m =>
            `<span style="background:${m.color};color:#fff;"
                   class="inline-flex items-center text-xs px-2 py-1 rounded-full">
                 ${escH(m.name)}
             </span>`
        ).join('');
        el.innerHTML = `
            <div class="mt-3 pt-3 flex flex-wrap gap-2 items-center"
                 style="border-top:1px solid var(--color-border)">
                <span class="text-xs" style="color:var(--color-text-secondary)">Менеджеры:</span>
                ${badges}
            </div>`;
    }

    // ── Сетка календаря ──────────────────────────────────────────────────────

    function renderCalendar() {
        const year     = currentDate.getFullYear();
        const month    = currentDate.getMonth();
        const today    = new Date(); today.setHours(0,0,0,0);
        const firstDay = new Date(year, month, 1);
        const lastDay  = new Date(year, month + 1, 0);
        const startDow = (firstDay.getDay() + 6) % 7;

        let html = `
            <div class="flex items-center justify-between mb-4">
                <button id="cal-prev" class="btn-primary px-3 py-1 rounded text-sm">&larr;</button>
                <span class="font-semibold text-lg">${MONTH_NAMES[month]} ${year}</span>
                <button id="cal-next" class="btn-primary px-3 py-1 rounded text-sm">&rarr;</button>
            </div>
            <div class="grid grid-cols-7 gap-1 text-center text-xs font-medium mb-1"
                 style="color:var(--color-text-secondary)">
                <div>Пн</div><div>Вт</div><div>Ср</div><div>Чт</div>
                <div>Пт</div><div>Сб</div><div>Вс</div>
            </div>
            <div class="grid grid-cols-7 gap-1">`;

        for (let i = 0; i < startDow; i++) html += '<div class="h-24 rounded"></div>';

        for (let day = 1; day <= lastDay.getDate(); day++) {
            const ds       = `${year}-${pad(month+1)}-${pad(day)}`;
            const isToday  = new Date(year,month,day).getTime() === today.getTime();
            const isSel    = ds === selectedDate;
            const dayEvts  = events.filter(e => e.date === ds);

            let border = 'border:1px solid var(--color-border);';
            if (isToday) border = 'border:2px solid var(--color-primary);';
            if (isSel)   border = 'border:2px solid #f59e0b; box-shadow:0 0 0 2px #fde68a55;';

            html += `<div class="h-24 rounded p-1 text-xs"
                          style="${border}background:var(--color-card);cursor:pointer;"
                          onclick="calDayClick('${ds}')">
                         <div class="font-medium mb-1"
                              style="color:${isToday?'var(--color-primary)':'var(--color-text)'}">
                             ${day}
                         </div>`;

            for (const ev of dayEvts.slice(0, 3)) {
                html += renderBadge(ev);
            }
            if (dayEvts.length > 3) {
                html += `<div style="color:var(--color-text-secondary);font-size:0.6rem;text-align:center">
                             +${dayEvts.length - 3}
                         </div>`;
            }
            html += '</div>';
        }
        html += '</div>';
        calendarEl.innerHTML = html;

        document.getElementById('cal-prev')?.addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() - 1);
            selectedDate = null; hideDayDetail(); renderCalendar();
        });
        document.getElementById('cal-next')?.addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() + 1);
            selectedDate = null; hideDayDetail(); renderCalendar();
        });
    }

    /**
     * Рендерит один бейдж события.
     * Для совместных задач — CSS-градиент 50/50.
     */
    function renderBadge(ev) {
        const isTask = ev.type === 'task';
        const icon   = isTask ? '✓ ' : '📦 ';
        const bg     = (isTask && ev.co_manager_color)
            ? `linear-gradient(90deg,${ev.color} 50%,${ev.co_manager_color} 50%)`
            : ev.color;
        const label  = escH(`${ev.title}${ev.manager ? ' · ' + ev.manager : ''}`)
                     + (ev.co_manager ? ` + ${escH(ev.co_manager)}` : '');
        const clickHandler = isTask
            ? `event.stopPropagation(); openTaskModal(${ev.task_id})`
            : '';

        return `<div class="truncate rounded px-1 mb-0.5"
                     title="${label}"
                     style="background:${bg};color:#fff;font-size:0.6rem;
                            cursor:pointer;transition:filter 0.15s;"
                     onmouseover="this.style.filter='brightness(1.3)'"
                     onmouseout="this.style.filter=''"
                     onclick="${clickHandler}">
                    ${icon}${escH(ev.title)}
                </div>`;
    }

    // ── Панель деталей дня ────────────────────────────────────────────────────

    window.calDayClick = function (ds) {
        if (selectedDate === ds) {
            selectedDate = null; hideDayDetail(); renderCalendar();
            return;
        }
        selectedDate = ds;
        renderCalendar();
        showDayDetail(ds);
    };

    function showDayDetail(ds) {
        const el = document.getElementById('day-detail');
        if (!el) return;
        const dayEvts = events.filter(e => e.date === ds);
        if (!dayEvts.length) { hideDayDetail(); return; }

        const [y, m, d] = ds.split('-').map(Number);
        const title = `${d} ${MONTH_GEN[m-1]} ${y}`;

        const cards = dayEvts.map(ev => {
            const bg     = (ev.type==='task' && ev.co_manager_color)
                ? `linear-gradient(90deg,${ev.color} 50%,${ev.co_manager_color} 50%)`
                : ev.color;
            const typeL  = ev.type === 'task' ? 'Задача' : 'Отгрузка';
            const prio   = ev.priority ? (PRIORITY_RU[ev.priority]  || ev.priority)  : null;
            const stat   = ev.status   ? (STATUS_RU[ev.status]      || ev.status)    : null;
            const co     = ev.co_manager
                ? `<span class="text-xs px-2 py-0.5 rounded-full ml-1"
                          style="background:${ev.co_manager_color};color:#fff;">
                       + ${escH(ev.co_manager)}
                   </span>` : '';

            return `<div class="p-3 rounded-lg mb-2"
                         style="border-left:4px solid ${ev.color};background:var(--color-bg,#f9fafb);">
                        <div class="flex items-start justify-between gap-2">
                            <div class="font-semibold text-sm">${escH(ev.title)}</div>
                            <span class="text-xs px-2 py-0.5 rounded-full shrink-0"
                                  style="background:${bg};color:#fff;">${typeL}</span>
                        </div>
                        <div class="text-xs mt-1 flex flex-wrap items-center gap-1"
                             style="color:var(--color-text-secondary)">
                            <span>${escH(ev.manager)}</span>${co}
                            ${ev.customer ? `<span>· ${escH(ev.customer)}</span>` : ''}
                        </div>
                        ${ev.equipment ? `<div class="text-xs mt-0.5" style="color:var(--color-text-secondary)">Оборудование: ${escH(ev.equipment)}</div>` : ''}
                        ${ev.description ? `<div class="text-xs mt-1">${escH(ev.description)}</div>` : ''}
                        ${ev.amount ? `<div class="text-xs mt-0.5" style="color:var(--color-text-secondary)">Сумма: ${Number(ev.amount).toLocaleString('ru-RU')} ₽</div>` : ''}
                        <div class="flex flex-wrap gap-2 mt-2">
                            ${prio ? `<span class="text-xs px-2 py-0.5 rounded" style="background:var(--color-surface,#f3f4f6)">Приоритет: ${prio}</span>` : ''}
                            ${stat ? `<span class="text-xs px-2 py-0.5 rounded" style="background:var(--color-surface,#f3f4f6)">Статус: ${stat}</span>` : ''}
                            ${ev.type==='task' ? `<button onclick="event.stopPropagation();openTaskModal(${ev.task_id})"
                                class="text-xs px-2 py-0.5 rounded hover:opacity-80"
                                style="background:var(--color-primary);color:#fff;">✏ Управление</button>` : ''}
                        </div>
                    </div>`;
        }).join('');

        el.innerHTML = `
            <div class="mt-4 p-4 rounded-lg" style="border:1px solid var(--color-border);background:var(--color-card);">
                <div class="flex items-center justify-between mb-3">
                    <h3 class="font-semibold text-sm">
                        События на <strong>${title}</strong>
                        <span class="ml-1 text-xs font-normal" style="color:var(--color-text-secondary)">(${dayEvts.length})</span>
                    </h3>
                    <button onclick="calCloseDayDetail()"
                            class="text-xl leading-none hover:opacity-60"
                            style="color:var(--color-text-secondary)">&times;</button>
                </div>
                ${cards}
            </div>`;
        el.scrollIntoView({ behavior:'smooth', block:'nearest' });
    }

    function hideDayDetail() {
        const el = document.getElementById('day-detail');
        if (el) el.innerHTML = '';
    }

    window.calCloseDayDetail = function () {
        selectedDate = null; hideDayDetail(); renderCalendar();
    };

    // ── Модальное окно управления задачей ─────────────────────────────────────

    let modalTaskId = null;

    function ensureModal() {
        if (document.getElementById('task-modal')) return;
        const m = document.createElement('div');
        m.id = 'task-modal';
        m.style.cssText = `
            display:none; position:fixed; inset:0; z-index:1000;
            background:rgba(0,0,0,0.5); align-items:center; justify-content:center;`;
        m.innerHTML = `
            <div id="task-modal-box"
                 style="background:var(--color-card); border-radius:12px;
                        padding:24px; width:min(520px,95vw); max-height:90vh;
                        overflow-y:auto; position:relative; box-shadow:0 8px 32px rgba(0,0,0,.3);">
                <button onclick="closeTaskModal()"
                        style="position:absolute;top:12px;right:14px;font-size:1.4rem;
                               line-height:1;background:none;border:none;cursor:pointer;
                               color:var(--color-text-secondary);">&times;</button>
                <div id="task-modal-content"></div>
            </div>`;
        m.addEventListener('click', e => { if (e.target === m) closeTaskModal(); });
        document.body.appendChild(m);
    }

    window.openTaskModal = async function (taskId) {
        ensureModal();
        modalTaskId = taskId;
        const ev = events.find(e => e.task_id === taskId);
        if (!ev) return;

        const prio     = ev.priority || 'medium';
        const empOpts  = employees.map(e =>
            `<option value="${e.id}" style="background:${e.color}">${escH(e.name)}</option>`
        ).join('');

        const managerBadge = `<span style="background:${ev.color};color:#fff;"
            class="inline-flex items-center text-xs px-2 py-1 rounded-full">
            ${escH(ev.manager)}</span>`;
        const coBadge = ev.co_manager
            ? `<span style="background:${ev.co_manager_color};color:#fff;"
                   class="inline-flex items-center text-xs px-2 py-1 rounded-full ml-1">
                   + ${escH(ev.co_manager)}
                   <button onclick="taskCoRemove()" title="Убрать"
                       style="margin-left:4px;font-size:0.8rem;opacity:0.7;background:none;border:none;cursor:pointer;color:#fff;">✕</button>
               </span>` : '';

        document.getElementById('task-modal-content').innerHTML = `
            <h3 class="font-bold text-base mb-1">${escH(ev.title)}</h3>
            <div class="flex flex-wrap items-center gap-1 mb-4 text-sm">
                ${managerBadge}${coBadge}
                <span style="color:var(--color-text-secondary);font-size:0.75rem;">
                    Срок: ${ev.date}
                </span>
            </div>

            <label class="block text-xs font-medium mb-1" style="color:var(--color-text-secondary)">Название</label>
            <input id="tm-title" type="text" value="${escH(ev.title)}"
                class="w-full px-3 py-2 rounded border text-sm mb-3"
                style="border-color:var(--color-border);background:var(--color-bg);color:var(--color-text);">

            <label class="block text-xs font-medium mb-1" style="color:var(--color-text-secondary)">Описание / Комментарий</label>
            <textarea id="tm-desc" rows="3"
                class="w-full px-3 py-2 rounded border text-sm mb-3"
                style="border-color:var(--color-border);background:var(--color-bg);color:var(--color-text);resize:vertical;">${escH(ev.description || '')}</textarea>

            <div class="grid grid-cols-2 gap-3 mb-4">
                <div>
                    <label class="block text-xs font-medium mb-1" style="color:var(--color-text-secondary)">Новый срок</label>
                    <input id="tm-date" type="date" value="${ev.date}"
                        class="w-full px-3 py-2 rounded border text-sm"
                        style="border-color:var(--color-border);background:var(--color-bg);color:var(--color-text);">
                </div>
                <div>
                    <label class="block text-xs font-medium mb-1" style="color:var(--color-text-secondary)">Приоритет</label>
                    <select id="tm-prio"
                        class="w-full px-3 py-2 rounded border text-sm"
                        style="border-color:var(--color-border);background:var(--color-bg);color:var(--color-text);">
                        <option value="low"      ${prio==='low'?'selected':''}>Низкий</option>
                        <option value="medium"   ${prio==='medium'?'selected':''}>Средний</option>
                        <option value="high"     ${prio==='high'?'selected':''}>Высокий</option>
                        <option value="critical" ${prio==='critical'?'selected':''}>Критический</option>
                    </select>
                </div>
            </div>

            <div class="flex flex-wrap gap-2 mb-4">
                <button onclick="taskSave()"
                    class="px-4 py-2 rounded text-sm font-medium hover:opacity-80"
                    style="background:var(--color-primary);color:#fff;">✏ Сохранить</button>
                <button onclick="taskCopy()"
                    class="px-4 py-2 rounded text-sm font-medium hover:opacity-80"
                    style="background:var(--color-secondary,#6b7280);color:#fff;">📋 Копировать</button>
                <button onclick="taskDelete()"
                    class="px-4 py-2 rounded text-sm font-medium hover:opacity-80"
                    style="background:var(--color-danger,#dc2626);color:#fff;">🗑 Удалить</button>
            </div>

            <hr style="border-color:var(--color-border);margin-bottom:12px;">

            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs font-medium mb-1" style="color:var(--color-text-secondary)">Передать коллеге</label>
                    <div class="flex gap-1">
                        <select id="tm-transfer"
                            class="flex-1 px-2 py-1.5 rounded border text-xs"
                            style="border-color:var(--color-border);background:var(--color-bg);color:var(--color-text);">
                            <option value="">— выбрать —</option>
                            ${empOpts}
                        </select>
                        <button onclick="taskTransfer()"
                            class="px-3 py-1.5 rounded text-xs hover:opacity-80"
                            style="background:var(--color-warning,#d97706);color:#fff;">→</button>
                    </div>
                </div>
                <div>
                    <label class="block text-xs font-medium mb-1" style="color:var(--color-text-secondary)">Исполнить вместе</label>
                    <div class="flex gap-1">
                        <select id="tm-co"
                            class="flex-1 px-2 py-1.5 rounded border text-xs"
                            style="border-color:var(--color-border);background:var(--color-bg);color:var(--color-text);">
                            <option value="">— выбрать —</option>
                            ${empOpts}
                        </select>
                        <button onclick="taskCoAssign()"
                            class="px-3 py-1.5 rounded text-xs hover:opacity-80"
                            style="background:var(--color-success,#16a34a);color:#fff;">+</button>
                    </div>
                </div>
            </div>
            <div id="tm-msg" class="mt-3 text-xs" style="color:var(--color-text-secondary);min-height:1.2em;"></div>
        `;

        const modal = document.getElementById('task-modal');
        modal.style.display = 'flex';
    };

    window.closeTaskModal = function () {
        const m = document.getElementById('task-modal');
        if (m) m.style.display = 'none';
        modalTaskId = null;
    };

    // Вспомогательная функция для AJAX-запросов к задаче
    async function taskApi(endpoint, body) {
        const res = await fetch(`/api/tasks/${modalTaskId}/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return res.json();
    }

    function tmMsg(text, ok = true) {
        const el = document.getElementById('tm-msg');
        if (el) {
            el.textContent = text;
            el.style.color = ok ? 'var(--color-success,#16a34a)' : 'var(--color-danger,#dc2626)';
        }
    }

    window.taskSave = async function () {
        const r = await taskApi('update', {
            title:       document.getElementById('tm-title').value,
            description: document.getElementById('tm-desc').value,
            due_date:    document.getElementById('tm-date').value,
            priority:    document.getElementById('tm-prio').value,
        });
        if (r.ok) { tmMsg('Сохранено'); closeTaskModal(); await loadEvents(); }
        else       tmMsg(r.error || 'Ошибка', false);
    };

    window.taskCopy = async function () {
        const r = await taskApi('copy', {});
        if (r.ok) { tmMsg('Задача скопирована'); closeTaskModal(); await loadEvents(); }
        else       tmMsg(r.error || 'Ошибка', false);
    };

    window.taskDelete = async function () {
        if (!confirm('Удалить задачу?')) return;
        const r = await taskApi('delete', {});
        if (r.ok) { closeTaskModal(); await loadEvents(); }
        else       tmMsg(r.error || 'Ошибка', false);
    };

    window.taskTransfer = async function () {
        const id = parseInt(document.getElementById('tm-transfer').value);
        if (!id) { tmMsg('Выберите менеджера', false); return; }
        const r = await taskApi('transfer', { manager_id: id });
        if (r.ok) { tmMsg('Задача передана'); closeTaskModal(); await loadEvents(); }
        else       tmMsg(r.error || 'Ошибка', false);
    };

    window.taskCoAssign = async function () {
        const id = parseInt(document.getElementById('tm-co').value);
        if (!id) { tmMsg('Выберите менеджера', false); return; }
        const r = await taskApi('co-assign', { manager_id: id });
        if (r.ok) { tmMsg('Соисполнитель добавлен'); closeTaskModal(); await loadEvents(); }
        else       tmMsg(r.error || 'Ошибка', false);
    };

    window.taskCoRemove = async function () {
        const r = await taskApi('co-remove', {});
        if (r.ok) { await loadEvents(); openTaskModal(modalTaskId); }
        else       tmMsg(r.error || 'Ошибка', false);
    };

    // ── Утилиты ───────────────────────────────────────────────────────────────

    function pad(n) { return String(n).padStart(2, '0'); }

    function escH(s) {
        if (!s) return '';
        return String(s)
            .replace(/&/g,'&amp;').replace(/</g,'&lt;')
            .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    loadEvents();
})();
