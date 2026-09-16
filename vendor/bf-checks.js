import * as THREE from 'three';

/**
 * 黑灯工厂手作品类的机械检验（三套引擎共用）——用户 2026-09-16 定的硬性规定：
 *  1. 生成过程中反复查穿模 + 查"不符合现实的建模"（部件散开、悬空的壶嘴/盖子/把手）；
 *  2. 背景别复杂、别跟主体重复（靠人工陈设约定 + 场景 dressing 标 loose）；
 *  3. 符合物理：液体只能从壶嘴出来、倾倒方向要对（壶嘴要比壶盖低）。
 */

/** 组装检验：每个 Group 的直接部件（Mesh 或子 Group）两两之间至少要挨着一个（包围盒膨胀 tol 后相交），否则就是"部件散开/悬空"。
 *  纯粹的集合（散落的饺子、浇头、陈设总组）在 userData.loose = true 里跳过。 */
export function checkAssembly(root, { tol = 0.03, minParts = 2 } = {}) {
  const out = []; root.updateMatrixWorld(true);
  root.traverse((g) => {
    if (!g.isGroup || g === root || !g.visible || g.userData.loose) return;
    const units = g.children.filter((c) => c.visible && ((c.isMesh && !c.isInstancedMesh) || c.isGroup));
    if (units.length < minParts) return;
    const boxes = units.map((u) => { const b = new THREE.Box3().setFromObject(u, true); return b.isEmpty() ? null : b; }); if (boxes.filter(Boolean).length < minParts) return;
    for (let i = 0; i < units.length; i++) {
      if (!boxes[i]) continue; const bi = boxes[i].clone().expandByScalar(tol); let ok = false;
      for (let j = 0; j < units.length; j++) { if (i === j || !boxes[j]) continue; if (bi.intersectsBox(boxes[j])) { ok = true; break; } }
      if (!ok) { const c = boxes[i].getCenter(new THREE.Vector3()); out.push(`${nameOf(g)}：第 ${i} 件${units[i].isGroup ? '子组' : '部件'}悬空（${units[i].geometry?.type || ''} @ ${c.x.toFixed(2)},${c.y.toFixed(2)},${c.z.toFixed(2)}）`); }
    }
  });
  return out;
}
function nameOf(g) { if (g.name) return g.name; if (g.userData.name) return g.userData.name; const p = g.getWorldPosition(new THREE.Vector3()); return `组@${p.x.toFixed(1)},${p.y.toFixed(1)},${p.z.toFixed(1)}`; }

/** 倒液物理：流柱正在出的时候，起点必须在壶嘴上；给了 ref（壶盖/后沿）的话壶嘴还得比它低（倾倒方向没反）。 */
export function pourPhysics(stream, spoutWorld, refWorld = null, label = '壶') {
  const out = []; if (!stream || !stream.on || (stream.flow ?? 1) <= 0.02 || !stream.mesh?.visible) return out;
  const d = stream.start.distanceTo(spoutWorld); if (d > 0.08) out.push(`${label}：流柱不是从壶嘴出来的（差 ${d.toFixed(2)}）`);
  if (refWorld && spoutWorld.y > refWorld.y + 0.02) out.push(`${label}：出水时壶嘴比壶盖/后沿还高（倾倒方向反了）`);
  return out;
}
