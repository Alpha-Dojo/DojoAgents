/** Scroll `element` inside a scrollable `container` without moving the page. */
export function scrollElementIntoScrollContainer(
  container: HTMLElement,
  element: HTMLElement,
  padding = 4,
): void {
  const containerRect = container.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();

  const topBound = containerRect.top + padding;
  const bottomBound = containerRect.bottom - padding;
  if (elementRect.top >= topBound && elementRect.bottom <= bottomBound) {
    return;
  }

  let delta = 0;
  if (elementRect.top < topBound) {
    delta = elementRect.top - topBound;
  } else if (elementRect.bottom > bottomBound) {
    delta = elementRect.bottom - bottomBound;
  }

  container.scrollBy({ top: delta, behavior: 'smooth' });
}
