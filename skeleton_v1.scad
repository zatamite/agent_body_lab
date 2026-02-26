// AGENTIC PARAMETERS: The AI modifies these to evolve
mount_type = "NEMA17"; 
bolt_diameter = 3.4;   // M3 clearance
wall_thickness = 3.5; 
internal_volume = [45, 45, 65]; 

module mechanical_core() {
    difference() {
        // Outer rigid chassis
        cube([internal_volume[0] + wall_thickness*2, 
              internal_volume[1] + wall_thickness*2, 
              internal_volume[2]], center=true);
        // Interior electronics cavity
        cube(internal_volume, center=true);
        // Cooling vents (Agent-added logic)
        for(i=[0:3]) rotate([0,0,i*90]) translate([25,0,0]) cube([10,20,40], center=true);
    }
}
mechanical_core();