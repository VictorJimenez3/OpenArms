// OpenArms v0.5: ONE COLOR, ONE PLATFORM, FOUR CUP SLOTS. Millimetres.
// Ordinary store-bought cups; no cup attachment or laboratory glassware required.
// These cup measurements are placeholders. Adjust after buying the actual cups.
part = "platform"; // platform or gauge; one material, no applied graphics
cup_bottom_d = 38;
cup_top_d = 48;
cup_height = 51;
// Per-slot overrides A, B, C, D; edit if mixing cup sizes.
slot_cups = [[cup_bottom_d,cup_top_d,cup_height],
             [cup_bottom_d,cup_top_d,cup_height],
             [cup_bottom_d,cup_top_d,cup_height],
             [cup_bottom_d,cup_top_d,cup_height]];
platform_width = 200;
platform_depth = 200;
base_thickness = 3;
guide_height = 6;
guide_wall = 3;
radial_clearance = 0.8;
opening_degrees = 120;
column_pitch = 90;
row_pitch = 82;
front_row_y = 78;
gauge_delta = 0;
$fn = 96;
eps = 0.02;

function center(i) = [platform_width/2+(i%2-0.5)*column_pitch,front_row_y+floor(i/2)*row_pitch];
function lower(d,delta=0) = d[0]+delta+2*radial_clearance;
function upper(d,delta=0) = lower(d,delta)+(d[1]-d[0])*guide_height/d[2];
function radius(d) = max(lower(d),upper(d))/2+guide_wall;
function label(i) = ["A","B","C","D"][i];
assert(len(slot_cups)==4,"Exactly four cup slots required");
assert(base_thickness>=2 && radial_clearance>0 && guide_wall>=2);
assert(opening_degrees>0 && opening_degrees<180);

module guide(d,delta=0) {
  assert(d[0]+delta>0 && d[1]>=d[0] && d[2]>guide_height);
  rotate([0,0,270+opening_degrees/2]) rotate_extrude(angle=360-opening_degrees)
    polygon([[lower(d,delta)/2,0],[lower(d,delta)/2+guide_wall,0],
             [upper(d,delta)/2+guide_wall,guide_height],[upper(d,delta)/2,guide_height]]);
}
module base() {
  linear_extrude(base_thickness) hull()
    for(x=[5,platform_width-5],y=[5,platform_depth-5]) translate([x,y]) circle(r=5);
}
module markings() {
  for(i=[0:3]) {
    p=center(i);
    translate([i%2==0 ? 15 : platform_width-15,p[1],base_thickness-0.6])
      linear_extrude(0.6+eps) text(label(i),size=8,halign="center",valign="center");
  }
  for(i=[0:10]) translate([platform_width/2-50+i*10,platform_depth-10,base_thickness-0.6])
    cube([0.7,i%5==0 ? 5 : 3,0.6+eps]);
  translate([platform_width/2,platform_depth-17,base_thickness-0.6])
    linear_extrude(0.6+eps) text("100 mm",size=4,halign="center");

}
module platform() {
  for(i=[0:3]) {
    p=center(i);r=radius(slot_cups[i]);
    assert(p[0]-r>24 && p[0]+r<platform_width-24,"Increase width/pitch to clear labels and edges");
    assert(p[1]-r>12,"Move cup row rearward to clear front edge");
    assert(p[1]+r<platform_depth-15,"Increase platform depth for ruler clearance");
    for(j=[0:3]) if(i<j) {
      q=center(j);dist=norm(p-q);
      assert(dist>radius(slot_cups[i])+radius(slot_cups[j])+4,"Guides overlap: increase pitch");
      assert(dist>(slot_cups[i][1]+slot_cups[j][1])/2+10,"Cup rims too close: increase pitch");
    }
  }
  difference() {
    union() {
      base();
      for(i=[0:3]) {
        p=center(i);
        translate([p[0],p[1],base_thickness-eps])
          scale([1,1,(guide_height+eps)/guide_height]) guide(slot_cups[i]);
      }
    }
    markings();
    for(x=[8,platform_width-8],y=[8,platform_depth-8])
      translate([x,y,-eps]) cylinder(d=3.6,h=base_thickness+2*eps);
  }
}
module gauge() {
  d=slot_cups[0];r=max(lower(d,gauge_delta),upper(d,gauge_delta))/2+guide_wall;
  difference() {
    union() {guide(d,gauge_delta);translate([-10,r-1,0]) cube([20,12,2]);}
    translate([0,r+5,1.4]) linear_extrude(0.7)
      text(str(d[0]+gauge_delta),size=4,halign="center",valign="center");
  }
}
if(part=="platform") platform();
else if(part=="gauge") gauge();
else if(part=="config") echo([platform_width,platform_depth,base_thickness,guide_height,guide_wall,radial_clearance,opening_degrees,slot_cups,[for(i=[0:3]) center(i)]]);
else assert(false,"Use platform or gauge");
