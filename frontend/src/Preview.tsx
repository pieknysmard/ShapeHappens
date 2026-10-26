import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

export type MeshData = { positions?: number[]; colors?: number[]; stl: string; preview_mode: 'cookie' | 'roller' };
export function Preview({ data, wireframe, grid, orthographic, action }: { data: MeshData | null; wireframe: boolean; grid: boolean; orthographic: boolean; action: number }) {
  const host = useRef<HTMLDivElement>(null);
  // Decode large STL files once per generated result, not again on each
  // wireframe, grid, camera or projection change.
  const geometry = useMemo(() => {
    let geometry = new THREE.BufferGeometry();
    if (data?.preview_mode === 'roller') {
      const decoded = atob(data.stl);
      const bytes = new Uint8Array(decoded.length);
      for (let i = 0; i < decoded.length; i++) bytes[i] = decoded.charCodeAt(i);
      geometry.dispose();
      geometry = new STLLoader().parse(bytes.buffer);
      geometry.computeBoundingBox();
    } else if (data?.positions && data.colors) {
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(data.positions, 3));
      geometry.setAttribute('color', new THREE.Float32BufferAttribute(data.colors, 3));
      geometry.computeVertexNormals();
      geometry.computeBoundingBox();
    }
    return geometry;
  }, [data]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => {
    const element = host.current!;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#e9eef2');
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    element.appendChild(renderer.domElement);
    const material = new THREE.MeshStandardMaterial({ vertexColors: data?.preview_mode === 'cookie', color: data?.preview_mode === 'roller' ? '#9eaec0' : '#ffffff', roughness: 0.78, metalness: 0, wireframe });
    const mesh = new THREE.Mesh(geometry, material);
    // Geometry is the decoded STL triangle list. No proxy geometry is used.
    if (data) scene.add(mesh);
    const bounds = geometry.boundingBox;
    const center = bounds?.getCenter(new THREE.Vector3()) ?? new THREE.Vector3();
    const size = bounds?.getSize(new THREE.Vector3()).length() ?? 120;
    const span = Math.max(size, 10);
    const camera: THREE.PerspectiveCamera | THREE.OrthographicCamera = orthographic
      ? new THREE.OrthographicCamera(-span, span, span, -span, 0.01, span * 30)
      : new THREE.PerspectiveCamera(40, 1, 0.01, span * 30);
    camera.up.set(0, 0, 1);
    camera.position.copy(center).add(new THREE.Vector3(span * 0.9, -span * 1.15, span * 1.1));
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.enableDamping = true;
    controls.update();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x626b78, 1.4));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(span, -span, span * 2);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.7);
    fill.position.set(-span, span, span);
    scene.add(fill);
    const helpers: THREE.Object3D[] = [];
    if (grid) {
      const plane = new THREE.GridHelper(Math.ceil(span / 10) * 10, 20, 0x9ba9b6, 0xcbd4dc);
      plane.rotation.x = Math.PI / 2;
      plane.position.z = (bounds?.min.z ?? 0) - 0.03;
      const axes = new THREE.AxesHelper(span * 0.35);
      helpers.push(plane, axes);
      scene.add(...helpers);
    }
    const resize = () => {
      const width = element.clientWidth, height = element.clientHeight;
      renderer.setSize(width, height);
      const aspect = width / height;
      if (camera instanceof THREE.PerspectiveCamera) camera.aspect = aspect;
      else { camera.left = -span * aspect * 0.75; camera.right = span * aspect * 0.75; camera.top = span * 0.75; camera.bottom = -span * 0.75; }
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element); resize();
    renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
    return () => {
      observer.disconnect(); controls.dispose(); renderer.setAnimationLoop(null);
      material.dispose();
      helpers.forEach(helper => { const h = helper as THREE.LineSegments; h.geometry.dispose(); const mats = Array.isArray(h.material) ? h.material : [h.material]; mats.forEach(m => m.dispose()); });
      renderer.dispose(); element.removeChild(renderer.domElement);
    };
  }, [data, geometry, wireframe, grid, orthographic, action]);
  return <div className="canvas" ref={host} aria-label="Interactive generated STL preview" />;
}
