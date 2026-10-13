package com.libertyrecomp;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Reads the supplied EFLC disc. Saves live outside the game directory. */
final class EflcIsoInstaller {
    static final String XEX_SHA = "590accf1a74b70ff3b4181090367fe702aa6a7a12059a04414d55c8ca514a140";
    private static final long[] PARTITIONS = {0, 0xFB20, 0x20600, 0x2080000, 0xFD90000};
    interface Progress { void update(long copied, long total, String file); }
    interface Validate { void check(File staged) throws Exception; }
    static final class Entry {
        final String path; final long offset, size; final boolean directory;
        Entry(String p, long o, long s, boolean d) { path=p;offset=o;size=s;directory=d; }
    }
    private static final class Directory {
        final String path; final long offset; final int size, depth;
        Directory(String p,long o,int s,int d) {path=p;offset=o;size=s;depth=d;}
    }
    private static boolean fits(long offset,long length,long total) {
        return offset>=0 && length>=0 && offset<=total && length<=total-offset;
    }
    private static ByteBuffer read(FileChannel source,long offset,int size) throws IOException {
        if (!fits(offset,size,source.size())) throw new IOException("ISO-bestand is afgebroken of beschadigd.");
        ByteBuffer bytes=ByteBuffer.allocate(size).order(ByteOrder.LITTLE_ENDIAN);
        while(bytes.hasRemaining()) {
            int n=source.read(bytes,offset+bytes.position());
            if(n<=0) throw new IOException("ISO kon niet volledig worden gelezen.");
        }
        bytes.flip();return bytes;
    }
    private static long u32(ByteBuffer b,int at) { return b.getInt(at)&0xFFFFFFFFL; }
    static List<Entry> inspect(FileChannel source) throws IOException {
        long base=-1;ByteBuffer descriptor=null;
        for(long candidate:PARTITIONS) {
            long offset=candidate+32*2048;
            if(!fits(offset,2048,source.size())) continue;
            ByteBuffer bytes=read(source,offset,2048);byte[] magic=new byte[20];bytes.get(magic);
            if(new String(magic,StandardCharsets.US_ASCII).equals("MICROSOFT*XBOX*MEDIA")) {base=candidate;descriptor=bytes;break;}
        }
        if(base<0) throw new IOException("Geen ondersteunde Xbox 360-ISO gevonden.");
        long rootSize=u32(descriptor,24);
        if(rootSize<14 || rootSize>16*1024*1024) throw new IOException("Ongeldige hoofdmap in ISO.");
        ArrayList<Directory> pending=new ArrayList<>();
        pending.add(new Directory("",base+u32(descriptor,20)*2048,(int)rootSize,0));
        Set<String> visitedDirectories=new HashSet<>();List<Entry> entries=new ArrayList<>();
        long directoryBytes=0;int nodeCount=0;
        while(!pending.isEmpty()) {
            Directory directory=pending.remove(pending.size()-1);
            if(directory.depth>256 || directory.size<14 || directory.size>16*1024*1024
                || !visitedDirectories.add(directory.offset+":"+directory.size)) throw new IOException("Ongeldige mapstructuur in ISO.");
            directoryBytes+=directory.size;
            if(directoryBytes>64*1024*1024) throw new IOException("Mapstructuur is te groot.");
            ByteBuffer bytes=read(source,directory.offset,directory.size);
            ArrayList<Integer> nodes=new ArrayList<>();nodes.add(0);
            Set<Integer> visited=new HashSet<>();Set<String> names=new HashSet<>();
            while(!nodes.isEmpty()) {
                int ordinal=nodes.remove(nodes.size()-1),at=ordinal*4;
                if(!visited.add(ordinal) || !fits(at,14,directory.size) || ++nodeCount>100000) throw new IOException("Ongeldige bestandslijst in ISO.");
                int left=bytes.getShort(at)&0xFFFF,right=bytes.getShort(at+2)&0xFFFF;
                long sector=u32(bytes,at+4),length=u32(bytes,at+8);
                boolean isDirectory=(bytes.get(at+12)&0x10)!=0;
                int nameLength=bytes.get(at+13)&0xFF;
                if(nameLength==0 || !fits(at+14,nameLength,directory.size)) throw new IOException("Afgebroken bestandsnaam.");
                byte[] rawName=new byte[nameLength];bytes.position(at+14);bytes.get(rawName);
                String name=new String(rawName,StandardCharsets.ISO_8859_1);
                if(name.equals(".") || name.equals("..") || name.matches(".*[\\\\/:\\x00-\\x1F].*")
                    || !names.add(name.toLowerCase(Locale.ROOT))) throw new IOException("Ongeldige of dubbele bestandsnaam.");
                String path=directory.path.isEmpty()?name:directory.path+"/"+name;
                long offset=base+sector*2048;
                if(!fits(offset,length,source.size())) throw new IOException("Bestand valt buiten de ISO.");
                entries.add(new Entry(path,offset,length,isDirectory));
                if(isDirectory && length>0) {
                    if(length>16*1024*1024) throw new IOException("Te grote map in ISO.");
                    pending.add(new Directory(path,offset,(int)length,directory.depth+1));
                }
                if(left!=0) nodes.add(left);if(right!=0) nodes.add(right);
            }
        }
        return entries;
    }
    static void install(FileChannel source,File game,Progress progress) throws Exception {
        installValidated(source,game,progress,staged -> {
            File xex=new File(staged,"default.xex");
            if(!xex.isFile() || xex.length()>64*1024*1024) throw new IOException("EFLC executable ontbreekt.");
            MessageDigest digest=MessageDigest.getInstance("SHA-256");
            try(java.io.FileInputStream stream=new java.io.FileInputStream(xex)) {
                byte[] bytes=new byte[1024*1024];int count;
                while((count=stream.read(bytes))!=-1) digest.update(bytes,0,count);
            }
            StringBuilder hex=new StringBuilder();for(byte b:digest.digest()) hex.append(String.format(Locale.ROOT,"%02x",b&255));
            if(!hex.toString().equals(XEX_SHA)) throw new IOException("Deze ISO bevat een andere executable dan de onderzochte EFLC-versie.");
            for(String path:new String[]{"common.rpf","xbox360.rpf","audio.rpf","DLC1/DLC.rpf","DLC2/DLC.rpf"})
                if(!new File(staged,path).isFile()) throw new IOException("EFLC-bestand ontbreekt: "+path);
        });
    }
    static void installValidated(FileChannel source,File game,Progress progress,Validate validate) throws Exception {
        List<Entry> entries=inspect(source);long total=0;
        for(Entry entry:entries) if(!entry.directory && !entry.path.startsWith("$SystemUpdate/")) total=Math.addExact(total,entry.size);
        File parent=game.getParentFile();if(!parent.isDirectory() && !parent.mkdirs()) throw new IOException("Installatiemap kon niet worden gemaakt.");
        if(parent.getUsableSpace()<total+256L*1024*1024) throw new IOException("Onvoldoende vrije opslag. Benodigd: "+(total/1024/1024)+" MB plus 256 MB.");
        File stage=new File(parent,"game.installing"),backup=new File(parent,"game.previous");
        // Only this installer's temporary game staging is removed. Saves are separate.
        delete(stage);if(!stage.mkdirs()) throw new IOException("Tijdelijke installatiemap kon niet worden gemaakt.");
        boolean committed=false;long copied=0;ByteBuffer buffer=ByteBuffer.allocate(1024*1024);
        try {
            String stagePath=stage.getCanonicalPath()+File.separator;
            for(Entry entry:entries) {
                if(entry.path.startsWith("$SystemUpdate/")) continue;
                File destination=new File(stage,entry.path);
                if(!destination.getCanonicalPath().startsWith(stagePath)) throw new IOException("Ongeldig doelpad.");
                if(entry.directory) {if(!destination.isDirectory() && !destination.mkdirs()) throw new IOException("Map kon niet worden gemaakt.");continue;}
                File folder=destination.getParentFile();if(!folder.isDirectory() && !folder.mkdirs()) throw new IOException("Map kon niet worden gemaakt.");
                try(FileOutputStream out=new FileOutputStream(destination)) {
                    long done=0;
                    while(done<entry.size) {
                        buffer.clear();buffer.limit((int)Math.min(buffer.capacity(),entry.size-done));
                        int n=source.read(buffer,entry.offset+done);
                        if(n<=0) throw new IOException("ISO lezen is onderbroken.");
                        out.write(buffer.array(),0,n);done+=n;copied+=n;
                        progress.update(copied,total,entry.path);
                    }
                    out.getFD().sync();
                }
            }
            validate.check(stage);
            delete(backup);
            if(game.exists() && !game.renameTo(backup)) throw new IOException("Bestaande spelinstallatie kon niet worden verplaatst.");
            if(!stage.renameTo(game)) {
                if(backup.exists() && !backup.renameTo(game)) throw new IOException("Installatie commit mislukt; de vorige spelbestanden staan in game.previous.");
                throw new IOException("Nieuwe spelinstallatie kon niet worden geplaatst.");
            }
            committed=true;delete(backup);
        } finally { if(!committed) delete(stage); }
    }
    private static void delete(File file) throws IOException {
        if(!file.exists()) return;
        if(file.isDirectory()) {
            File[] files=file.listFiles();if(files==null) throw new IOException("Tijdelijke map kon niet worden gelezen.");
            for(File child:files) delete(child);
        }
        if(!file.delete()) throw new IOException("Tijdelijk bestand kon niet worden verwijderd: "+file.getName());
    }
}
