#include "KisExiv2IODevice.h"
#include <QCoreApplication>
#include <cassert>
#include <iostream>
#include <vector>
int main(int argc,char **argv) {
 QCoreApplication app(argc,argv);
 const QString fixture="/fixtures/synthetic-bayer.dng";
 KisExiv2IODevice io(fixture);
 const std::string &path=io.path();
 std::vector<std::string> churn(10000,std::string(100,'X'));
 assert(path==fixture.toStdString()); assert(&path==&io.path());
 assert(io.open()==0);assert(io.isopen());assert(io.size()>0);
 Exiv2::byte buffer[4];assert(io.read(buffer,4)==4);
 const Exiv2::byte byte=0;assert(io.write(&byte,1)==0);
 io.close();assert(path==fixture.toStdString());
 auto image=Exiv2::ImageFactory::open(KisExiv2IODevice::ptr_type(new KisExiv2IODevice(fixture)));
 image->readMetadata();assert(!image->exifData().empty());
 bool caught=false;
 try {auto missing=Exiv2::ImageFactory::open(KisExiv2IODevice::ptr_type(new KisExiv2IODevice("/fixtures/absent.dng")));}
 catch(const Exiv2::Error &error){caught=true;std::string text=error.what();assert(text.find("absent.dng")!=std::string::npos);}
 assert(caught);std::cout<<"stable path, readonly metadata, refused write, missing-file exception PASS\n";
}
