const MIN_DRAWER_HEIGHT = 180;
const MAX_DRAWER_RATIO = 0.72;
const DEFAULT_DRAWER_RATIO = 0.34;

export function getDrawerBounds(containerHeight: number): {
  minHeight: number;
  maxHeight: number;
} {
  const safeContainerHeight = Math.max(containerHeight, MIN_DRAWER_HEIGHT + 40);
  const maxHeight = Math.max(
    MIN_DRAWER_HEIGHT,
    Math.floor(safeContainerHeight * MAX_DRAWER_RATIO)
  );
  const minHeight = Math.min(MIN_DRAWER_HEIGHT, maxHeight);
  return { minHeight, maxHeight };
}

export function clampDrawerHeight(
  height: number,
  containerHeight: number
): number {
  const { minHeight, maxHeight } = getDrawerBounds(containerHeight);
  return Math.min(Math.max(Math.round(height), minHeight), maxHeight);
}

export function getDefaultDrawerHeight(containerHeight: number): number {
  const target = Math.floor(containerHeight * DEFAULT_DRAWER_RATIO);
  return clampDrawerHeight(target, containerHeight);
}

export function resizeDrawerHeight(
  startHeight: number,
  deltaY: number,
  containerHeight: number
): number {
  return clampDrawerHeight(startHeight - deltaY, containerHeight);
}
