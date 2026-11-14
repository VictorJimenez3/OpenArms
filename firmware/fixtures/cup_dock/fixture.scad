// OpenArms cup fixture v0.3. All lengths millimetres. Not physically qualified.
// Edit the six cup dimensions below; diameter is OUTER diameter at the base.
// Export part="source", "receiver", "gauge_source", or "gauge_receiver".
// Individual gauge: part="gauge_single", gauge_cup="source", gauge_delta=0.
// assembly is a visual mock-up only, never a print file or robot reach claim.
part = "source";
source_bottom_d = 38; // ENGINEERING PLACEHOLDER. Target does not publish the base OD.
source_top_d = 48; // Published overall width; rim interpretation needs measurement.
source_height = 51; // Published Diamond 2 oz overall height, Target TCIN 94991464.
receiver_bottom_d = 59;
receiver_top_d = 73.7;
receiver_height = 63.5;
radial_clearance = 0.8;
guide_height = 6;
guide_wall = 3;
base_thickness = 3;
opening_degrees = 120;
tile_width = 100;
tile_depth = 132;
cup_center = [50,88];
marker_center = [50,26];
marker_black_size = 36;
marker_paper_size = 44;
layout_pitch = 125; // Preview only. Place and teach on the real bench.
gauge_cup = "source";
gauge_delta = 0; // Changes bottom and top diameters equally, not clearance.
$fn = 96;
eps = 0.02;

function cup_dims(kind) = kind=="source" ? [source_bottom_d,source_top_d,source_height] : [receiver_bottom_d,receiver_top_d,receiver_height];
function inner_bottom(d,delta=0) = d[0]+delta+2*radial_clearance;
function inner_top(d,delta=0) = d[0]+delta+(d[1]-d[0])*guide_height/d[2]+2*radial_clearance;

module guide(d,delta=0) {
  assert(d[2]>guide_height && d[1]>=d[0] && d[0]+delta>0);
  assert(radial_clearance>0 && guide_wall>=2 && guide_height>=3);
  assert(opening_degrees>0 && opening_degrees<180);
  // 240-degree tapered U, open toward -Y. TOP-DROP ONLY, not a slide-in slot.
  rotate([0,0,270+opening_degrees/2]) rotate_extrude(angle=360-opening_degrees)
    polygon([[inner_bottom(d,delta)/2,0],
      [inner_bottom(d,delta)/2+guide_wall,0],
      [inner_top(d,delta)/2+guide_wall,guide_height],
      [inner_top(d,delta)/2,guide_height]]);
}

module plate(w,h,t,r=4) {
  linear_extrude(t) hull() for(x=[r,w-r],y=[r,h-r]) translate([x,y]) circle(r=r);
}

module engravings(label) {
  // Recessed marks; fill with dark paint if desired. Ruler is planar only.
  for(i=[0:10]) translate([5,20+i*10,base_thickness-0.6])
    cube([i%5==0 ? 7 : 4,0.7,0.6+eps]);
  for(item=[["0",15],["100",125]]) translate([15,item[1],base_thickness-0.6])
    linear_extrude(0.6+eps) text(item[0],size=3,valign="center");
  translate([85,33,base_thickness-0.6]) linear_extrude(0.6+eps)
    text(label,size=10,halign="center",valign="center");
  // Four engraved corner crosses outside 44 mm paper. Do not cover white margin.
  for(sx=[-1,1],sy=[-1,1]) translate([marker_center[0]+sx*23,marker_center[1]+sy*23,base_thickness-0.6]) {
    translate([-1.5,-0.35,0]) cube([3,0.7,0.6+eps]);
    translate([-0.35,-1.5,0]) cube([0.7,3,0.6+eps]);
  }
}

module dock(kind) {
  d=cup_dims(kind);
  r=max(inner_bottom(d),inner_top(d))/2+guide_wall;
  assert(cup_center[0]-r>13 && cup_center[0]+r<tile_width-4,"Increase tile width/move cup; ruler needs clearance");
  assert(cup_center[1]+r<tile_depth-4,"Increase tile depth");
  assert(cup_center[1]-r>marker_center[1]+marker_paper_size/2+3,"Move marker and cup apart");
  difference() {
    union() {
      plate(tile_width,tile_depth,base_thickness);
      // Small overlap ensures a single solid; total guide top is base+guide.
      translate([cup_center[0],cup_center[1],base_thickness-eps])
        scale([1,1,(guide_height+eps)/guide_height]) guide(d);
    }
    engravings(kind=="source" ? "A" : "C");
    // M3 clearance holes OR tape strips across the flat margins; no hardware required.
    for(x=[9,tile_width-9],y=[7,tile_depth-7]) translate([x,y,-eps]) cylinder(d=3.6,h=base_thickness+2*eps);
  }
}

module gauge(kind,delta=0) {
  // Exact guide, no floor. Cup and gauge sit on the same flat table.
  // Difference of ground planes does not change the relative guide/cup fit.
  d=cup_dims(kind);
  r=max(inner_bottom(d,delta),inner_top(d,delta))/2+guide_wall;
  difference() {
    union() {
      guide(d,delta);
      translate([-10,r-1,0]) cube([20,12,2]);
    }
    translate([0,r+5,1.4]) linear_extrude(0.7)
      text(str(d[0]+delta),size=4,halign="center",valign="center");
  }
}

module gauge_set(kind) {
  // Labels are assumed CUP bottom diameters; bore includes 1.6 mm diametral clearance.
  for(i=[0:2]) translate([i*(cup_dims(kind)[0]+16),0,0]) gauge(kind,(i-1)*2);
}

module cup_visual(d) {
  color([0.70,0.85,0.94,0.25]) difference() {
    cylinder(h=d[2],d1=d[0],d2=d[1]);
    translate([0,0,0.8]) cylinder(h=d[2],d1=d[0]-1.2,d2=d[1]-1.2);
  }
}

if(part=="source") dock("source");
else if(part=="receiver") dock("receiver");
else if(part=="gauge_source") gauge_set("source");
else if(part=="gauge_receiver") gauge_set("receiver");
else if(part=="gauge_single") gauge(gauge_cup,gauge_delta);
else if(part=="assembly") for(i=[0:1]) translate([i*layout_pitch,0,0]) {
  color(i==0 ? [0.08,0.42,0.48] : [0.20,0.29,0.43]) dock(i==0 ? "source" : "receiver");
  translate([cup_center[0],cup_center[1],base_thickness]) cup_visual(cup_dims(i==0 ? "source" : "receiver"));
  color("white") translate([marker_center[0]-22,marker_center[1]-22,base_thickness]) cube([44,44,0.1]);
}
else assert(false,"Unknown part");
