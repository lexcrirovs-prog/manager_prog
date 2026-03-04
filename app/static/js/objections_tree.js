/**
 * Интерактивное дерево возражений (mindmap-стиль).
 * Загружает данные из /api/objections-tree и рендерит раскрывающееся дерево.
 */
(function() {
    const container = document.getElementById('objections-tree-container');
    if (!container) return;

    async function loadTree() {
        try {
            const resp = await fetch('/api/objections-tree');
            const tree = await resp.json();
            container.innerHTML = renderNodes(tree, 0);
            attachListeners();
        } catch (e) {
            container.innerHTML = '<p style="color: var(--color-danger)">Ошибка загрузки дерева возражений</p>';
        }
    }

    function renderNodes(nodes, depth) {
        if (!nodes || nodes.length === 0) return '';

        const colors = [
            'var(--color-primary)',
            'var(--color-accent)',
            'var(--color-success)',
            'var(--color-danger)',
        ];
        const color = colors[depth % colors.length];

        let html = '<ul class="ml-4 space-y-1">';
        for (const node of nodes) {
            const hasChildren = node.children && node.children.length > 0;
            const icon = hasChildren ? '▸' : '•';

            html += `
                <li class="tree-item" data-id="${node.id}">
                    <div class="flex items-start gap-2 p-2 rounded cursor-pointer hover:opacity-80 transition-opacity"
                         style="border-left: 3px solid ${color}; background: var(--color-card);"
                         data-toggle="${node.id}">
                        <span class="toggle-icon font-mono text-sm mt-0.5" style="color: ${color}; min-width: 1rem;">${icon}</span>
                        <div class="flex-1 min-w-0">
                            <div class="font-medium text-sm" style="color: var(--color-text)">${escapeHtml(node.title)}</div>
                            ${node.response ? `<div class="text-xs mt-1" style="color: var(--color-text-secondary)">${escapeHtml(node.response)}</div>` : ''}
                            ${node.category ? `<span class="inline-block mt-1 px-2 py-0.5 rounded text-xs" style="background: var(--color-primary-light); color: var(--color-primary)">${escapeHtml(node.category)}</span>` : ''}
                        </div>
                        <div class="flex gap-1 shrink-0">
                            <button class="edit-obj px-1 text-xs rounded" style="color: var(--color-primary)" title="Редактировать" data-id="${node.id}" data-title="${escapeAttr(node.title)}" data-response="${escapeAttr(node.response || '')}" data-category="${escapeAttr(node.category || '')}">✎</button>
                            <form method="POST" action="/knowledge/objections/${node.id}/delete" class="inline" onsubmit="return confirm('Удалить узел и все дочерние?')">
                                <button type="submit" class="px-1 text-xs" style="color: var(--color-danger)" title="Удалить">✕</button>
                            </form>
                        </div>
                    </div>
                    ${hasChildren ? `<div class="children hidden" data-children="${node.id}">${renderNodes(node.children, depth + 1)}</div>` : ''}
                </li>
            `;
        }
        html += '</ul>';
        return html;
    }

    function attachListeners() {
        // Раскрытие/сворачивание
        container.querySelectorAll('[data-toggle]').forEach(el => {
            el.addEventListener('click', function(e) {
                if (e.target.closest('.edit-obj') || e.target.closest('form')) return;
                const id = this.dataset.toggle;
                const children = container.querySelector(`[data-children="${id}"]`);
                const icon = this.querySelector('.toggle-icon');
                if (children) {
                    children.classList.toggle('hidden');
                    icon.textContent = children.classList.contains('hidden') ? '▸' : '▾';
                }
            });
        });

        // Редактирование
        container.querySelectorAll('.edit-obj').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const modal = document.getElementById('edit-objection-modal');
                if (!modal) return;
                document.getElementById('edit-obj-id').value = this.dataset.id;
                document.getElementById('edit-obj-title').value = this.dataset.title;
                document.getElementById('edit-obj-response').value = this.dataset.response;
                document.getElementById('edit-obj-category').value = this.dataset.category;
                document.getElementById('edit-obj-form').action = `/knowledge/objections/${this.dataset.id}/edit`;
                modal.classList.remove('hidden');
            });
        });
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeAttr(str) {
        return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    loadTree();
})();
