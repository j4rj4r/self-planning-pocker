export type CardCount = Map<string, number>;

export interface RoundStats {
  counts: CardCount;
  average: number;
  agreement: number;
}

export function computeRoundStats(hands: number[]): RoundStats {
  const counts: CardCount = new Map();
  let sum = 0;
  for (const hand of hands) {
    const key = hand.toString();
    counts.set(key, (counts.get(key) || 0) + 1);
    sum += hand;
  }

  const average = sum / hands.length || 0;
  const agreement = Math.max(0, ...counts.values()) / hands.length || 0;

  return { counts, average, agreement };
}
