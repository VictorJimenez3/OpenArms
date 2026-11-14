#!/usr/bin/env python3
"""Read-only structural review for a static, visual-only laboratory USD asset.

Usage: python validate_usd.py scene.usd [--require-self-contained]
       [--expect-proxy /World/RobotProxy] [--allow-no-camera]
Requires Pixar's pxr modules (e.g. pip install usd-core in a supported Python).
Only JSON is emitted on stdout; USD diagnostics may appear on stderr.
"""
import argparse
import json
import math
import os
import sys


def inspect(args):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade, UsdUtils

    report = {"file": os.path.abspath(args.usd), "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]
    stage = Usd.Stage.Open(report["file"], load=Usd.Stage.LoadAll)
    if not stage:
        raise RuntimeError("USD stage could not be opened")
    report["usd_version"] = list(Usd.GetVersion())
    report["metersPerUnit"] = UsdGeom.GetStageMetersPerUnit(stage)
    report["upAxis"] = str(UsdGeom.GetStageUpAxis(stage))
    default = stage.GetDefaultPrim()
    report["defaultPrim"] = str(default.GetPath()) if default else None
    if not stage.HasAuthoredMetadata("metersPerUnit") or not math.isclose(report["metersPerUnit"], 1.0, abs_tol=1e-9):
        errors.append("metersPerUnit must be explicitly authored as 1")
    if not stage.HasAuthoredMetadata("upAxis") or report["upAxis"] != "Z":
        errors.append("upAxis must be explicitly authored as Z")
    if not default or not default.IsDefined() or not default.IsActive() or default.GetParent() != stage.GetPseudoRoot():
        errors.append("A defined, active root defaultPrim is required")
    composition = [str(e) for e in stage.GetCompositionErrors()]
    report["composition_errors"] = composition
    if composition:
        errors.append("Stage has composition errors")

    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(Sdf.AssetPath(report["file"]))
    root = stage.GetRootLayer()
    external_layers = [l.identifier for l in layers if l.identifier != root.identifier]
    report["dependencies"] = {"layers": [l.identifier for l in layers], "assets": list(assets), "unresolved": list(unresolved)}
    if unresolved:
        errors.append("Unresolved asset dependencies")
    report["self_contained_single_layer"] = not external_layers and not assets and not unresolved
    if not report["self_contained_single_layer"]:
        (errors if args.require_self_contained else warnings).append("USD depends on external layers or assets; distribute dependencies or package USDZ")

    # Inspect authored specs, including inactive prims and unselected variants.
    # Match unknown PhysX schemas too, without needing a PhysX plugin installed.
    physics = []
    authored_assets = []
    def forbidden(name):
        value = str(name).lower()
        return value.startswith(("physics", "physx")) or "articulation" in value

    for layer in layers:
        def visit(path):
            spec = layer.GetObjectAtPath(path)
            if isinstance(spec, Sdf.PrimSpec):
                schemas = spec.GetInfo("apiSchemas") if spec.HasInfo("apiSchemas") else None
                items = list(schemas.GetAppliedItems()) if schemas else []
                # Deleted list-op entries are not applied schemas.
                matches = [s for s in [spec.typeName] + items if forbidden(s)]
                if matches:
                    physics.append({"layer": layer.identifier, "path": str(path), "schemas": matches})
            elif isinstance(spec, Sdf.PropertySpec) and forbidden(spec.name):
                physics.append({"layer": layer.identifier, "path": str(path), "property": spec.name})
        layer.Traverse(Sdf.Path.absoluteRootPath, visit)
        # This visits asset-valued metadata, arrays, and time samples without
        # changing any paths (or saving layers).
        def record_asset(path):
            if path:
                authored_assets.append({"layer": layer.identifier, "path": path})
            return path
        # ModifyAssetPaths is intentionally run on a disposable copy only.
        scratch = Sdf.Layer.CreateAnonymous()
        scratch.TransferContent(layer)
        UsdUtils.ModifyAssetPaths(scratch, record_asset)
    report["authored_asset_paths"] = authored_assets
    report["absolute_asset_paths"] = [a for a in authored_assets if os.path.isabs(a["path"]) or "://" in a["path"]]
    if report["absolute_asset_paths"]:
        warnings.append("Absolute or URI asset paths may be nonportable")
    report["physics_or_articulation"] = physics
    if physics:
        errors.append("Physics/articulation schemas or properties are forbidden for this visual-only asset")

    time = Usd.TimeCode(args.time) if args.time is not None else Usd.TimeCode.Default()
    report["bounds_time"] = args.time if args.time is not None else "default"
    cache = UsdGeom.BBoxCache(time, [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy], useExtentsHint=False, ignoreVisibility=True)
    meshes, cameras, lights, proxies, materials = [], [], [], [], []
    total = Gf.Range3d()
    prims = list(Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()))
    for prim in prims:
        path = str(prim.GetPath())
        if prim.IsA(UsdGeom.Imageable):
            imageable = UsdGeom.Imageable(prim)
            purpose = str(imageable.ComputePurpose())
            proxy_target = imageable.GetProxyPrimRel().GetTargets()
            if purpose == "proxy" or "proxy" in prim.GetName().lower() or proxy_target:
                proxies.append({"path": path, "purpose": purpose, "proxyPrim_targets": [str(p) for p in proxy_target]})
            for target in proxy_target:
                if not stage.GetPrimAtPath(target):
                    errors.append("Unresolved proxyPrim target: " + str(target))
        if prim.IsA(UsdGeom.Camera):
            cameras.append(path)
        if prim.HasAPI(UsdLux.LightAPI):
            light = UsdLux.LightAPI(prim)
            lights.append({"path": path, "type": prim.GetTypeName(), "intensity": light.GetIntensityAttr().Get(time), "exposure": light.GetExposureAttr().Get(time), "normalize": light.GetNormalizeAttr().Get(time)})
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            points = mesh.GetPointsAttr().Get(time)
            counts = mesh.GetFaceVertexCountsAttr().Get(time)
            indices = mesh.GetFaceVertexIndicesAttr().Get(time)
            if points is None or counts is None or indices is None or not len(points) or not len(counts):
                errors.append("Empty or incomplete mesh: " + path)
                continue
            valid, reason = UsdGeom.Mesh.ValidateTopology(indices, counts, len(points))
            if not valid:
                errors.append("Invalid mesh topology " + path + ": " + reason)
            if not all(math.isfinite(float(v)) for point in points for v in point):
                errors.append("Nonfinite mesh points: " + path)
            bound = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            bounds = None
            if bound.IsEmpty() or not all(math.isfinite(float(v)) for p in [bound.GetMin(), bound.GetMax()] for v in p):
                errors.append("Empty or nonfinite world bound: " + path)
            else:
                total.UnionWith(bound)
                bounds = {"min": list(bound.GetMin()), "max": list(bound.GetMax()), "size": list(bound.GetSize())}
            material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            meshes.append({"path": path, "points": len(points), "faces": len(counts), "world_bounds": bounds, "material": str(material.GetPath()) if material else None})
        if prim.IsA(UsdShade.Material):
            material = UsdShade.Material(prim)
            source, _, _ = material.ComputeSurfaceSource()
            shader_id = source.GetIdAttr().Get() if source else None
            entry = {"path": path, "universal_surface_shader": str(source.GetPath()) if source else None, "shader_id": shader_id}
            if shader_id != "UsdPreviewSurface":
                errors.append("Material lacks a universal UsdPreviewSurface output: " + path)
            else:
                opacity = source.GetInput("opacity")
                threshold = source.GetInput("opacityThreshold")
                entry["opacity"] = opacity.Get(time) if opacity else 1.0
                entry["opacity_connected"] = bool(opacity and opacity.HasConnectedSource())
                entry["opacityThreshold"] = threshold.Get(time) if threshold else 0.0
                if entry["opacity_connected"] or (entry["opacity"] is not None and entry["opacity"] < 1.0):
                    warnings.append("Transparency needs target-renderer inspection: " + path)
            materials.append(entry)

    report.update(mesh_count=len(meshes), meshes=meshes, materials=materials, cameras=cameras, lights=lights, proxies=proxies)
    report["world_mesh_bounds"] = None if total.IsEmpty() else {"min": list(total.GetMin()), "max": list(total.GetMax()), "size": list(total.GetSize())}
    if not meshes:
        errors.append("No nonempty meshes found")
    if not materials:
        errors.append("No materials found")
    if not cameras and not args.allow_no_camera:
        errors.append("No camera found")
    unbound = [m["path"] for m in meshes if m["material"] is None]
    if unbound:
        warnings.append("Meshes without a mesh-level material binding (inspect subsets/displayColor): " + ", ".join(unbound))
    if not proxies:
        warnings.append("No purpose=proxy, proxy-named prim, or proxyPrim relationship found")
    for expected in args.expect_proxy:
        prim = stage.GetPrimAtPath(expected)
        if not prim or not prim.IsActive() or not prim.IsDefined():
            errors.append("Required proxy path missing or inactive: " + expected)
    if lights:
        warnings.append("UsdLux presence does not establish photometric or renderer equivalence")
    report["limitations"] = ["Static geometry/material/bounds inspection at the selected time only; default is the default time", "Proxy naming is heuristic unless --expect-proxy is supplied; proxy geometry is not a collider", "Does not render, evaluate texture pixels, prove complete shader-network support, or validate physical/robot capability", "Composed traversal uses selected variants; authored physics/dependencies are also inspected across layer specs"]
    report["ok"] = not errors
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("usd")
    parser.add_argument("--require-self-contained", action="store_true")
    parser.add_argument("--expect-proxy", action="append", default=[])
    parser.add_argument("--allow-no-camera", action="store_true")
    parser.add_argument("--time", type=float)
    args = parser.parse_args()
    try:
        report = inspect(args)
    except Exception as exc:
        report = {"file": os.path.abspath(args.usd), "ok": False, "errors": [type(exc).__name__ + ": " + str(exc)]}
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
