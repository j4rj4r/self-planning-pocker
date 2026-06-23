export type CardCount = Map<string, number>;

export interface RoundStats {
  counts: CardCount;
  average: number;
  agreement: number;
}

export function computeRoundStats(hands: number[]): RoundStats {
  const counts: CardCount = hands.reduce((previous, current) => {
    const key = current.toString();
    previous.set(key, (previous.get(key) || 0) + 1);
    return previous;
  }, new Map() as CardCount);

  const average = hands.reduce((previous, current) => previous + current, 0) / hands.length || 0;
  const agreement = Math.max(0, ...counts.values()) / hands.length || 0;

  return { counts, average, agreement };
}
