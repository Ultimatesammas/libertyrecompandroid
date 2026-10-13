package com.libertyrecomp;

import java.io.File;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;

public final class EflcIsoInstallerTest {
    static int checks;
    static void check(boolean ok,String why) {checks++;if(!ok) throw new AssertionError(why);}
    static ByteBuffer entry(String name,long sector,int size,boolean directory,int right) {
        byte[] n=name.getBytes(StandardCharsets.ISO_8859_1);
        ByteBuffer b=ByteBuffer.allocate(64).order(ByteOrder.LITTLE_ENDIAN);
        b.putShort((short)0).putShort((short)right).putInt((int)sector).putInt(size).put((byte)(directory?16:0)).put((byte)n.length).put(n);
        return b;
    }
    static File fixture(File root,boolean large) throws Exception {
        File file=new File(root,"fixture.iso");
        long base=large?0xFD90000:0,sector=large?2100000:50;
        try(RandomAccessFile out=new RandomAccessFile(file,"rw")) {
            out.setLength(0);
            out.setLength(large?9L*1024*1024*1024:200000);
            ByteBuffer h=ByteBuffer.allocate(2048).order(ByteOrder.LITTLE_ENDIAN);
            h.put("MICROSOFT*XBOX*MEDIA".getBytes(StandardCharsets.US_ASCII));h.putInt(40).putInt(128);
            out.seek(base+65536);out.write(h.array());
            out.seek(base+40*2048);out.write(entry("default.xex",sector,128,false,16).array());
            out.write(entry("DLC1",60,64,true,0).array());
            out.seek(base+60*2048);out.write(entry("DLC.rpf",70,16,false,0).array());
            out.seek(base+sector*2048);byte[] data=new byte[128];for(int i=0;i<data.length;i++)data[i]=(byte)i;out.write(data);
            out.seek(base+70*2048);out.write("synthetic-data!!".getBytes(StandardCharsets.US_ASCII));
        }
        return file;
    }
    static void mustFail(RunnableWithException action,String name) throws Exception {
        boolean failed=false;try{action.run();}catch(java.io.IOException e){failed=true;}check(failed,name);
    }
    interface RunnableWithException {void run() throws Exception;}
    public static void main(String[] args) throws Exception {
        File root=Files.createTempDirectory("eflc-installer-test-").toFile();
        File iso=fixture(root,false),game=new File(root,"EFLC/game"),saves=new File(root,"EFLC/saves");
        saves.mkdirs();Files.writeString(new File(saves,"save.dat").toPath(),"save must survive");
        try(RandomAccessFile input=new RandomAccessFile(iso,"r")) {
            check(EflcIsoInstaller.inspect(input.getChannel()).size()==3,"nested disc inventory");
            EflcIsoInstaller.installValidated(input.getChannel(),game,(a,b,c)->{},staged->{
                check(new File(staged,"default.xex").length()==128,"complete executable copy");
                check(new File(staged,"DLC1/DLC.rpf").length()==16,"nested archive copy");
            });
            check(new File(game,"default.xex").isFile(),"committed game");
            byte[] prior=Files.readAllBytes(new File(game,"default.xex").toPath());
            mustFail(()->EflcIsoInstaller.installValidated(input.getChannel(),game,(a,b,c)->{},staged->{throw new java.io.IOException("validation rejection");}),"validation rejection");
            check(Arrays.equals(prior,Files.readAllBytes(new File(game,"default.xex").toPath())),"previous game survives rejection");
            check(!new File(root,"EFLC/game.installing").exists(),"failed stage removed");
            mustFail(()->EflcIsoInstaller.install(input.getChannel(),game,(a,b,c)->{}),"wrong production executable rejected");
            check(Arrays.equals(prior,Files.readAllBytes(new File(game,"default.xex").toPath())),"production rejection preserves game");
        }
        check(Files.readString(new File(saves,"save.dat").toPath()).equals("save must survive"),"saves survive installs and rejection");
        File large=fixture(root,true);
        try(RandomAccessFile input=new RandomAccessFile(large,"r")) {
            var entries=EflcIsoInstaller.inspect(input.getChannel());
            check(entries.stream().anyMatch(e->e.offset>0xFFFFFFFFL),"64-bit offset beyond 4 GiB");
        }
        // Modify a fixture in place: invalid binary tree, out-of-range data and traversal.
        fixture(root,false);
        try(RandomAccessFile out=new RandomAccessFile(iso,"rw")) {out.seek(40*2048+64+2);out.write(new byte[]{16,0});}
        try(RandomAccessFile in=new RandomAccessFile(iso,"r")) {mustFail(()->EflcIsoInstaller.inspect(in.getChannel()),"directory node cycle rejected");}
        fixture(root,false);
        try(RandomAccessFile out=new RandomAccessFile(iso,"rw")) {out.seek(40*2048+4);out.write(new byte[]{-1,-1,-1,-1});}
        try(RandomAccessFile in=new RandomAccessFile(iso,"r")) {mustFail(()->EflcIsoInstaller.inspect(in.getChannel()),"out-of-bounds extent rejected");}
        fixture(root,false);
        try(RandomAccessFile out=new RandomAccessFile(iso,"rw")) {out.seek(40*2048);out.write(entry("../evil.xex",50,128,false,16).array());}
        try(RandomAccessFile in=new RandomAccessFile(iso,"r")) {mustFail(()->EflcIsoInstaller.inspect(in.getChannel()),"traversal rejected");}
        System.out.println("PASS "+checks+" installer checks; device save/load remains untested");
    }
}
