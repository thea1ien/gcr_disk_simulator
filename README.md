A python program that lets you pick a target .G64 disk image, and visually display the raw binary data the same way that
a real 1541 reads physical disks. It will let you see the binary data on the track, decode the binary into GCR data,
then decode the GCR data into a standard PETSCII byte data. Then searches for the header SYNC data, decode that into
the information for identifying the track and upcoming sector data, then read the upcoming actual sector data.
