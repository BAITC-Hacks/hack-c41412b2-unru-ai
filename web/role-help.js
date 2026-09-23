'use strict';
const roleHelp = {
  coordinator: ['Координирующий узел', 'Входящие и исходящие связи, достижимость от нескольких исходных узлов. Кандидат на структурно важную роль, не доказанный организатор.'],
  consolidator: ['Точка консолидации', 'Многие → один. Получает средства от нескольких отправителей при ограниченном исходящем распределении.'],
  distributor: ['Распределитель', 'Один → многие. Отправляет средства множеству получателей.'],
  transit: ['Транзитный узел', 'Пришло ≈ ушло. Наблюдаемые суммы входа и выхода близки. Передача именно тех же денег и последовательность переводов этой ролью не доказаны.'],
  terminal: ['Предполагаемый конечный получатель', 'Повторные поступления без видимого выхода. Это гипотеза в пределах выгрузки; на четвёртом колене эту роль не назначаем.'],
  peripheral: ['Периферийный узел', 'Пороги остальных ролей не достигнуты. Это не означает, что узел безопасен или неважен.']
};
const roleHelpPopup = document.createElement('div');
roleHelpPopup.id = 'role-help-popup';
roleHelpPopup.className = 'role-help-popup';
roleHelpPopup.setAttribute('role', 'tooltip');
roleHelpPopup.hidden = true;
document.body.append(roleHelpPopup);
let roleHelpAnchor = null;
let roleHelpPinned = false;
function closeRoleHelp() {
  roleHelpAnchor?.setAttribute('aria-pressed', 'false');
  roleHelpAnchor = null;
  roleHelpPinned = false;
  roleHelpPopup.hidden = true;
}
function showRoleHelp(button) {
  if (roleHelpPinned) return;
  roleHelpAnchor = button;
  roleHelpPopup.textContent = roleHelp[button.dataset.roleHelp][1];
  roleHelpPopup.hidden = false;
  const rect = button.getBoundingClientRect();
  const box = roleHelpPopup.getBoundingClientRect();
  roleHelpPopup.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - box.width - 12))}px`;
  roleHelpPopup.style.top = `${Math.max(12, rect.bottom + box.height + 20 < innerHeight ? rect.bottom + 8 : rect.top - box.height - 8)}px`;
}
function renderRoleLegend(colors) {
  closeRoleHelp();
  const legend = document.getElementById('role-legend');
  legend.replaceChildren();
  Object.keys(colors).forEach(role => {
    const item = document.createElement('span');
    item.className = 'role-legend-item';
    const dot = document.createElement('i');
    dot.className = 'role-dot';
    dot.style.background = colors[role];
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'role-help-button';
    button.textContent = 'ⓘ';
    button.dataset.roleHelp = role;
    button.setAttribute('aria-label', `Пояснение: ${roleHelp[role][0]}`);
    button.setAttribute('aria-describedby', roleHelpPopup.id);
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('pointerenter', event => { if (event.pointerType !== 'touch') showRoleHelp(button); });
    button.addEventListener('pointerleave', () => { if (!roleHelpPinned && document.activeElement !== button) closeRoleHelp(); });
    button.addEventListener('focus', () => showRoleHelp(button));
    button.addEventListener('blur', () => { if (!roleHelpPinned) closeRoleHelp(); });
    button.addEventListener('click', () => {
      if (roleHelpPinned && roleHelpAnchor === button) { closeRoleHelp(); return; }
      closeRoleHelp();
      showRoleHelp(button);
      roleHelpPinned = true;
      button.setAttribute('aria-pressed', 'true');
    });
    item.append(dot, document.createTextNode(roleHelp[role][0]), button);
    legend.append(item);
  });
}
document.addEventListener('pointerdown', event => {
  if (!event.target.closest('.role-help-button') && !roleHelpPopup.contains(event.target)) closeRoleHelp();
});
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeRoleHelp(); });
document.addEventListener('scroll', () => {
  if (!roleHelpPinned && roleHelpAnchor && document.activeElement === roleHelpAnchor) showRoleHelp(roleHelpAnchor);
  else closeRoleHelp();
}, true);
window.addEventListener('resize', closeRoleHelp);
