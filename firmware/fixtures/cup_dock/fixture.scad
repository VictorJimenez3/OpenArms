// OpenArms two-vessel fixture. All CAD dimensions are in millimetres.
part = "platform"; // platform, gauge, config
gauge_index = 0; // 0 = donor A, 1 = receiver C
gauge_radial_adjustment = 0; // positive values loosen the fit, mm per side

// Standalone defaults reproduce revision 2 of the photo-derived vessels.
// build.py reads the original vessel parameters and passes them to OpenSCAD.
vessel_profiles = [
    [[0,14.5],[1,15.2],[3,15.5],[45,17.5],[48.5,17.5],[50,20.5],[51,20.5]],
    [[0,29.5],[1.2,29.5],[3,30.5],[29,38],[30.5,39],[32,39]]
];
base_envelope_diameters = [31,59];
// Each entry is [height, circular rim OD, opening ID, spout projection].
vessel_dimensions = [[51,41,34,4],[32,78,75,0]];
donor_grip_band = [10,40]; // provisional, above the vessel's support plane

platform_size = [170,156];
printer_bed = [180,180]; // design target, confirm actual usable area
bed_margin = 4;         // reserved on each side
deck = 4;
centers = [[42,76],[116,80]];
guide_heights = [3.5,4.5];
guide_openings = [110,60]; // total angle, centred at -Y
radial_clearances = [0.65,0.75];
guide_wall = 2.6; // minimum radial wall at the chamfered top
chamfer_heights = [1.4,1.5];
chamfer_reliefs = [1,1.1];
seat_margin = 2.3;
donor_spout_deg = atan2(centers[1][1]-centers[0][1],centers[1][0]-centers[0][0]);

pad_size = 40;
pad_corner_radius = 1.5;
pad_recess = 0.4;
paper_pocket = 37;
marker_edge = 27; // length of the black square, including the black border
marker_quiet = marker_edge/6; // one white module around a 4x4 tag
marker_ids = [20,21,22,23]; // front left, front right, rear left, rear right
marker_centers = [
    [pad_size/2,pad_size/2],[platform_size[0]-pad_size/2,pad_size/2],
    [pad_size/2,platform_size[1]-pad_size/2],
    [platform_size[0]-pad_size/2,platform_size[1]-pad_size/2]
];

mount_centers = [[79,48],[79,111]];
mount_diameter = 3.6; // M3 clearance
mount_bar_width = 14;
tie_width = 20;
pad_rib_width = 15;
gauge_floor = 1.4;
$fn = 120;
eps = 0.03;

function r_at(profile, z, i=1) =
    let(p=profile[i-1], q=profile[i])
    z <= q[0] ? p[1]+(q[1]-p[1])*(z-p[0])/(q[0]-p[0]) :
    r_at(profile,z,i+1);

function vessel_r(i,z) = max(base_envelope_diameters[i]/2,r_at(vessel_profiles[i],z));
function bore_r(i,z,extra=0) =
    vessel_r(i,z)+radial_clearances[i]+extra +
    chamfer_reliefs[i] * max(0,(z-chamfer_start(i))/chamfer_heights[i]);
function chamfer_start(i) = guide_heights[i]-chamfer_heights[i];
function guide_r(i,extra=0) = bore_r(i,guide_heights[i],extra)+guide_wall;
function seat_r(i,extra=0) = guide_r(i,extra)+seat_margin;
function bore_profile(i,extra=0) =
    let(z_start=chamfer_start(i), h=guide_heights[i],
        breakpoints=concat([0],
            [for(p=vessel_profiles[i]) if(p[0]>0 && p[0]<z_start) p[0]],
            [z_start],
            [for(p=vessel_profiles[i]) if(p[0]>z_start && p[0]<h) p[0]],
            [h]))
    [for(z=breakpoints) [z,bore_r(i,z,extra)]];
function label_center(i) = centers[i]+[0,-vessel_dimensions[i][1]/2-8];
function inside_board(p,margin) =
    min(p)>=margin && p[0]<=platform_size[0]-margin && p[1]<=platform_size[1]-margin;
function rim_clear_of_pad(i,p) =
    let(dx=max(abs(centers[i][0]-p[0])-paper_pocket/2,0),
        dy=max(abs(centers[i][1]-p[1])-paper_pocket/2,0))
    norm([dx,dy])>vessel_dimensions[i][1]/2+vessel_dimensions[i][3]+1;

module geometry_checks() {
    assert(deck >= 3 && guide_wall >= 2.4 && seat_margin >= 2);
    assert(marker_edge>0 && bed_margin>=0);
    assert(len(marker_ids)==4 && len(marker_centers)==4);
    for(i=[0:3]) {
        assert(marker_ids[i]==floor(marker_ids[i]) && marker_ids[i]>=0 && marker_ids[i]<50);
        assert(len(search(marker_ids[i],marker_ids,0))==1,"Marker IDs must be unique");
        p=marker_centers[i];
        assert(inside_board(p,pad_size/2));
        for(j=[0:3]) if(i<j) {
            q=marker_centers[j];
            assert(max(abs(p[0]-q[0]),abs(p[1]-q[1]))>=pad_size,
                   "Marker pads must occupy separate locations");
        }
    }
    assert(paper_pocket >= marker_edge+2*marker_quiet+0.8);
    assert(paper_pocket <= pad_size-2*pad_corner_radius);
    assert(deck-pad_recess >= 3 && pad_recess > 0);
    assert(platform_size[0]+2*bed_margin <= printer_bed[0] &&
           platform_size[1]+2*bed_margin <= printer_bed[1],
           "Plate and margins exceed configured printer bed");
    assert(norm(centers[0]-centers[1]) >
           (vessel_dimensions[0][1]+vessel_dimensions[1][1])/2+
           vessel_dimensions[0][3]+6, "Provide a gap between vessel rim envelopes");
    for(i=[0:1]) {
        assert(inside_board(centers[i],seat_r(i)) && inside_board(label_center(i),6));
        assert(guide_heights[i]>chamfer_heights[i] && chamfer_heights[i]>0 &&
               chamfer_reliefs[i]>0);
        bore=bore_profile(i);
        for(j=[1:len(bore)-1])
            assert(bore[j][1]>=bore[j-1][1],"Guide bore must widen upward for vertical release");
        assert(guide_openings[i]>0 && guide_openings[i]<150);
        assert(radial_clearances[i]>0 && vessel_dimensions[i][0]>guide_heights[i]);
        for(p=marker_centers) assert(rim_clear_of_pad(i,p), "A vessel overhangs a marker pocket");
        for(p=mount_centers)
            assert(norm(centers[i]-p)>seat_r(i)+5,
                   "Mount hole too close to a seat");
    }
    for(p=mount_centers) {
        assert(inside_board(p,mount_bar_width/2));
        for(q=marker_centers)
            assert(max(abs(p[0]-q[0]),abs(p[1]-q[1]))>paper_pocket/2+5,
                   "Mount hardware must clear the marker pocket");
    }
    children();
}

module guide(i,extra=0) {
    profile=bore_profile(i,extra);
    r=guide_r(i,extra);
    h=guide_heights[i];
    rotate([0,0,270+guide_openings[i]/2])
        rotate_extrude(angle=360-guide_openings[i])
            polygon(concat([[profile[0][1],-eps],[r,-eps],[r,h]],
                           [for(j=[len(profile)-1:-1:0]) [profile[j][1],profile[j][0]]]));
}

module brace(p,q,width) {
    hull() for(pos=[p,q]) translate(pos) circle(d=width);
}

module pad(p) {
    translate(p) hull()
        for(x=[-1,1],y=[-1,1])
            translate([x,y]*(pad_size/2-pad_corner_radius))
                circle(r=pad_corner_radius);
}

module footprint() {
    for(i=[0:1]) {
        translate(centers[i]) circle(r=seat_r(i));
        brace(centers[i],label_center(i),12);
        for(j=[i,i+2]) brace(centers[i],marker_centers[j],pad_rib_width);
    }
    for(p=marker_centers) pad(p);
    brace(centers[0],centers[1],tie_width);
    brace(mount_centers[0],mount_centers[1],mount_bar_width);
}

module label_cutout(label,p,z) {
    translate([p[0],p[1],z-0.45])
        linear_extrude(0.45+eps)
            text(label,size=5,halign="center",valign="center");
}

module spout_arrow() {
    // Matching witness mark for the vertical modelled spout. Yaw is set by hand.
    p=centers[0];
    translate([p[0],p[1],deck-0.45]) rotate([0,0,donor_spout_deg])
        translate([seat_r(0)+1,0,0]) linear_extrude(0.45+eps)
            polygon([[0,-0.5],[4,-0.5],[4,-1.7],[7,0],[4,1.7],[4,0.5],[0,0.5]]);
}

module platform() {
    difference() {
        union() {
            linear_extrude(deck) footprint();
            for(i=[0:1]) translate([centers[i][0],centers[i][1],deck]) guide(i);
        }
        for(p=mount_centers)
            translate([p[0],p[1],-eps]) cylinder(d=mount_diameter,h=deck+2*eps);
        for(p=marker_centers)
            translate([p[0]-paper_pocket/2,p[1]-paper_pocket/2,deck-pad_recess])
                cube([paper_pocket,paper_pocket,pad_recess+eps]);
        for(i=[0:1]) label_cutout(["A","C"][i],label_center(i),deck);
        spout_arrow();
    }
}

module gauge(i,extra) {
    assert(i==0 || i==1,"Use gauge index 0 (A) or 1 (C)");
    assert(radial_clearances[i]+extra>0);
    translate([seat_r(i,extra),seat_r(i,extra),0])
        union() {
            cylinder(r=seat_r(i,extra),h=gauge_floor);
            translate([0,0,gauge_floor]) guide(i,extra);
        }
}

if (part == "platform") geometry_checks() platform();
else if (part == "gauge") gauge(gauge_index,gauge_radial_adjustment);
else if (part == "config") geometry_checks() echo([
    ["platform_size",platform_size],["printer_bed",printer_bed],["bed_margin",bed_margin],
    ["deck",deck],["centers",centers],["guide_heights",guide_heights],
    ["guide_wall",guide_wall],["guide_openings",guide_openings],
    ["radial_clearances",radial_clearances],["chamfer_heights",chamfer_heights],
    ["chamfer_reliefs",chamfer_reliefs],["gauge_floor",gauge_floor],
    ["bore_profiles",[for(i=[0:1]) bore_profile(i)]],
    ["guide_radii",[for(i=[0:1]) guide_r(i)]],["seat_radii",[for(i=[0:1]) seat_r(i)]],
    ["label_centers",[for(i=[0:1]) label_center(i)]],
    ["vessel_profiles",vessel_profiles],["vessel_dimensions",vessel_dimensions],
    ["base_envelope_diameters",base_envelope_diameters],["donor_grip_band",donor_grip_band],
    ["donor_spout_deg",donor_spout_deg],["marker_centers",marker_centers],
    ["marker_ids",marker_ids],["pad_size",pad_size],["paper_pocket",paper_pocket],
    ["marker_edge",marker_edge],["marker_quiet",marker_quiet],["pad_recess",pad_recess],
    ["tie_width",tie_width],["pad_rib_width",pad_rib_width],["mount_bar_width",mount_bar_width],
    ["mount_centers",mount_centers],["mount_diameter",mount_diameter]
]);
else assert(false,"Unknown part");
