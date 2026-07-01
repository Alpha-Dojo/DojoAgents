export function getPortfolioRailLabel(name: string): string {
  const firstLetter = Array.from(name).find((character) => /\p{L}/u.test(character));
  if (!firstLetter) return '?';

  return Array.from(firstLetter.toLocaleUpperCase())[0] ?? '?';
}
