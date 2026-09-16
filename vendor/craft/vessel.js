import * as THREE from 'three';
import { dropletTexture } from './textures.js';

// 器皿尺寸由主题配置（configureGlass），台面 y=0。内壁半径 = 外半径 − wall。
export const GLASS = { rTop: 0.92, rBot: 0.78, h: 3.1, wall: 0.05, baseH: 0.28, baseY: 0.0, material: 'glass' };
export function configureGlass(v) {
  Object.assign(GLASS, v); GLASS.baseY = 0;
  GLASS.innerBottom = GLASS.baseY + GLASS.baseH; GLASS.innerTop = GLASS.baseY + GLASS.h;
}
configureGlass({});

/** 某高度处的内壁半径 */
export function innerRadiusAt(y) {
  const k = THREE.MathUtils.clamp((y - GLASS.innerBottom) / (GLASS.h - GLASS.baseH), 0, 1);
  return THREE.MathUtils.lerp(GLASS.rBot, GLASS.rTop, k) - GLASS.wall;
}
/** 杯壁中心线半径（果片切口要卡的位置） */
export function wallRadiusAt(y) { return innerRadiusAt(y) + GLASS.wall / 2; }

// 第二组游戏的器皿由 cup.js 构建；这里只保留“主器皿尺寸”供瓶子/流柱的穿模托高与内壁守卫使用。
