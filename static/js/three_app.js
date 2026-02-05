// UniSolar 3D Designer Engine
import * as THREE from 'https://cdn.skypack.dev/three@0.132.2';
import { OrbitControls } from 'https://cdn.skypack.dev/three@0.132.2/examples/jsm/controls/OrbitControls.js';

class Solar3DApp {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, this.container.clientWidth / this.container.clientHeight, 0.1, 1000);
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });

        this.panels = [];
        this.features = [];
        this.roof = null;

        this.init();
    }

    init() {
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.renderer.shadowMap.enabled = true;
        this.container.appendChild(this.renderer.domElement);

        this.camera.position.set(10, 10, 10);
        this.controls = new OrbitControls(this.camera, this.renderer.domElement);

        // Lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        this.scene.add(ambientLight);

        this.sun = new THREE.DirectionalLight(0xffffff, 1.0);
        this.sun.position.set(20, 30, 10);
        this.sun.castShadow = true;
        this.sun.shadow.mapSize.width = 2048;
        this.sun.shadow.mapSize.height = 2048;
        this.scene.add(this.sun);

        // Ground/Grid
        const grid = new THREE.GridHelper(50, 50, 0x888888, 0x444444);
        this.scene.add(grid);

        // Background
        this.scene.background = new THREE.Color(0xf3f4f6);

        // Interaction
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        this.selectedObject = null;
        this.dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

        window.addEventListener('mousedown', (e) => this.onMouseDown(e));
        window.addEventListener('mousemove', (e) => this.onMouseMove(e));
        window.addEventListener('mouseup', () => this.onMouseUp());
        window.addEventListener('resize', () => this.onResize());
        this.animate();

        // Initial Objects
        this.createRoof('gable', 12, 8, 3, 15);
    }

    onMouseDown(event) {
        this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);
        const intersects = this.raycaster.intersectObjects(this.panels.concat(this.features));

        if (intersects.length > 0) {
            this.selectedObject = intersects[0].object;
            this.controls.enabled = false;
        }
    }

    onMouseMove(event) {
        if (!this.selectedObject) return;

        this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);

        // Snap to roof surface if possible
        const intersects = this.raycaster.intersectObject(this.roof, true);
        if (intersects.length > 0) {
            const intersection = intersects[0];
            const point = intersection.point;
            this.selectedObject.position.copy(point);
            this.selectedObject.position.y += 0.05; // Offset

            // Align rotation with roof normal
            const faceNormal = intersection.face.normal.clone();
            const worldNormal = faceNormal.transformDirection(this.roof.matrixWorld);

            // Align object's UP vector with world normal
            this.selectedObject.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), worldNormal);

            // Re-apply original Y rotation if it's a panel (optional, but good for custom orientation)
            // For now, let's keep it simple.
        }
    }

    onMouseUp() {
        this.selectedObject = null;
        this.controls.enabled = true;
    }

    onResize() {
        this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }

    createRoof(type, width, length, height, tiltDeg) {
        if (this.roof) this.scene.remove(this.roof);

        const group = new THREE.Group();
        const material = new THREE.MeshStandardMaterial({ color: 0x4b5563, side: THREE.DoubleSide });
        const tiltRad = (tiltDeg * Math.PI) / 180;
        const halfWidth = width / 2;
        const halfLength = length / 2;
        const ridgeHeight = halfWidth * Math.tan(tiltRad);

        let geometry = new THREE.BufferGeometry();
        let vertices = [];

        if (type === 'flat') {
            const flatGeo = new THREE.BoxGeometry(width, 0.2, length);
            const mesh = new THREE.Mesh(flatGeo, material);
            mesh.position.y = height;
            mesh.receiveShadow = true;
            group.add(mesh);
        } else if (type === 'gable') {
            // Left Slope
            vertices.push(-halfWidth, height, -halfLength, 0, height + ridgeHeight, -halfLength, 0, height + ridgeHeight, halfLength);
            vertices.push(-halfWidth, height, -halfLength, 0, height + ridgeHeight, halfLength, -halfWidth, height, halfLength);
            // Right Slope
            vertices.push(halfWidth, height, -halfLength, 0, height + ridgeHeight, halfLength, 0, height + ridgeHeight, -halfLength);
            vertices.push(halfWidth, height, -halfLength, halfWidth, height, halfLength, 0, height + ridgeHeight, halfLength);

            geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
            geometry.computeVertexNormals();
            const mesh = new THREE.Mesh(geometry, material);
            mesh.receiveShadow = true;
            group.add(mesh);
        } else if (type === 'hip') {
            const ridgeOffset = halfLength * 0.4;
            // Front
            vertices.push(-halfWidth, height, halfLength, halfWidth, height, halfLength, 0, height + ridgeHeight, halfLength - ridgeOffset);
            // Back
            vertices.push(-halfWidth, height, -halfLength, 0, height + ridgeHeight, -halfLength + ridgeOffset, halfWidth, height, -halfLength);
            // Left
            vertices.push(-halfWidth, height, -halfLength, -halfWidth, height, halfLength, 0, height + ridgeHeight, halfLength - ridgeOffset);
            vertices.push(-halfWidth, height, -halfLength, 0, height + ridgeHeight, halfLength - ridgeOffset, 0, height + ridgeHeight, -halfLength + ridgeOffset);
            // Right
            vertices.push(halfWidth, height, -halfLength, 0, height + ridgeHeight, halfLength - ridgeOffset, halfWidth, height, halfLength);
            vertices.push(halfWidth, height, -halfLength, 0, height + ridgeHeight, -halfLength + ridgeOffset, 0, height + ridgeHeight, halfLength - ridgeOffset);

            geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
            geometry.computeVertexNormals();
            const mesh = new THREE.Mesh(geometry, material);
            mesh.receiveShadow = true;
            group.add(mesh);
        }

        this.roof = group;
        this.scene.add(this.roof);
    }

    setAzimuth(degrees) {
        if (this.roof) {
            this.roof.rotation.y = (degrees * Math.PI) / 180;
        }
    }

    addPanel(x, y, z) {
        const geometry = new THREE.BoxGeometry(1.1, 0.05, 2.0);
        const material = new THREE.MeshStandardMaterial({ color: 0x1e3a8a });
        const panel = new THREE.Mesh(geometry, material);
        panel.position.set(x, y, z);
        panel.castShadow = true;
        this.scene.add(panel);
        this.panels.push(panel);
    }

    addFeature(type, x, z) {
        let geometry;
        if (type === 'chimney') {
            geometry = new THREE.BoxGeometry(0.8, 2.0, 0.8);
        } else {
            geometry = new THREE.CylinderGeometry(0.2, 0.2, 1.0);
        }
        const material = new THREE.MeshStandardMaterial({ color: 0x9ca3af });
        const feature = new THREE.Mesh(geometry, material);
        feature.position.set(x, 5, z); // Approximate height, should snap to roof
        feature.castShadow = true;
        this.scene.add(feature);
        this.features.push(feature);
    }

    getData() {
        return {
            panels: this.panels.map((p, i) => ({
                id: `p${i}`,
                x: p.position.x,
                y: p.position.z, // Mapping Three.js Z to 2D Y
                rotation: p.rotation.y
            })),
            features: this.features.map((f, i) => ({
                type: f.geometry.type === 'BoxGeometry' ? 'chimney' : 'vent',
                x: f.position.x,
                y: f.position.z,
                width: 0.8,
                height: 2.0,
                depth: 0.8
            }))
        };
    }
}

export default Solar3DApp;
