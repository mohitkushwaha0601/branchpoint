/**
 * Act indices for the Manyworlds scene.
 *
 * Its own module so neither `ForkScene` nor `ManyworldsSection` has to export a
 * constant alongside a component — that combination breaks fast refresh, and
 * both files need these names.
 */
export const ACT = {
  REALITY: 0,
  FORK: 1,
  EXECUTE: 2,
  OUTCOMES: 3,
  SETTLE: 4,
} as const;
