import type { KeyboardEvent } from 'react';

/**
 * onKeyDown handler that lets a non-`<button>` element which is clickable — a row
 * `<div>` or a `<tr>` wired with `onClick` — activate on Enter / Space, the way a real
 * button does. Pair it with `tabIndex={0}` and a button/option role.
 *
 * The event is ignored when it bubbled up from a nested control (e.g. a Delete button
 * inside the row), so the row action does not fire on top of the inner one.
 */
export function activateOnKey(activate: () => void) {
  return (e: KeyboardEvent) => {
    if (e.currentTarget !== e.target) return;
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      activate();
    }
  };
}
