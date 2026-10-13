package com.libertyrecomp;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;

/** Separate start-test installer; it never uses the GTA IV TU8 installer. */
public final class EflcLauncherActivity extends Activity {
    private TextView status;private Button choose,install,play;
    private Uri source;private File root;private boolean busy;private File selectedLog;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        File base=getExternalFilesDir(null);if(base==null) base=getFilesDir();root=new File(base,"EFLC");
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(24,20,24,20);
        TextView title=new TextView(this);title.setText("Episodes from Liberty City — Start Test");title.setTextSize(24);layout.addView(title);
        TextView note=new TextView(this);note.setText("Experimentele build. Starten, gameplay, opslaan en FPS zijn nog niet op jouw Thor bevestigd. Gebruik je eigen onderzochte EFLC-ISO.");layout.addView(note);
        status=new TextView(this);status.setTextIsSelectable(true);layout.addView(status);
        choose=button(layout,"Kies EFLC ISO",()->{
            Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT);intent.setType("*/*");intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);startActivityForResult(intent,1);
        });
        install=button(layout,"Installeer",this::install);
        play=button(layout,"Start EFLC",()->{
            Intent intent=new Intent(this,EflcGameActivity.class);intent.putExtra(LibertyActivity.EXTRA_DEBUG_LOG,true);startActivity(intent);
        });
        button(layout,"Exporteer debuglog",()->{
            selectedLog=null;File logBase=getExternalFilesDir(null);if(logBase==null) logBase=getFilesDir();
            File[] files=new File(logBase,"debug_logs").listFiles();
            if(files!=null) for(File file:files) if(file.isFile() && file.getName().endsWith(".log")
                && (selectedLog==null || file.lastModified()>selectedLog.lastModified())) selectedLog=file;
            if(selectedLog==null){status.setText("Nog geen debuglog. Start het spel eerst.");return;}
            Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.setType("text/plain");intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.putExtra(Intent.EXTRA_TITLE,"EFLC-debug.log");startActivityForResult(intent,2);
        });
        setContentView(layout);refresh();
    }
    private Button button(LinearLayout layout,String text,Runnable action) {
        Button button=new Button(this);button.setText(text);button.setOnClickListener(v->action.run());layout.addView(button);return button;
    }
    private void refresh() {
        boolean ready=new File(root,"game/default.xex").isFile();
        choose.setEnabled(!busy);install.setEnabled(!busy && source!=null);play.setEnabled(!busy && ready);
        if(!busy) status.setText(ready?"Spelbestanden geïnstalleerd. De app gebruikt een eigen opslagmap.":"Selecteer je ISO. Title Update 8 is niet nodig voor deze EFLC-starttest.");
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request==1 && result==RESULT_OK && data!=null && data.getData()!=null) {
            source=data.getData();
            try{getContentResolver().takePersistableUriPermission(source,Intent.FLAG_GRANT_READ_URI_PERMISSION);}catch(Exception ignored){}
            refresh();status.setText("ISO geselecteerd. Tik op Installeer.");
        }
        if(request==2 && result==RESULT_OK && data!=null && data.getData()!=null && selectedLog!=null) {
            try(FileInputStream in=new FileInputStream(selectedLog);
                java.io.OutputStream out=getContentResolver().openOutputStream(data.getData())) {
                if(out==null) throw new java.io.IOException("Doelbestand kon niet worden geopend.");
                byte[] bytes=new byte[65536];int count;while((count=in.read(bytes))!=-1) out.write(bytes,0,count);
                status.setText("Debuglog geëxporteerd. Je kunt dat bestand in de chat uploaden.");
            }catch(Exception error){status.setText("Export mislukt: "+error.getMessage());}
        }
    }
    private void install() {
        if(busy || source==null) return;busy=true;refresh();status.setText("ISO controleren…");
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        new Thread(()->{
            String outcome;
            try {
                ParcelFileDescriptor descriptor=getContentResolver().openFileDescriptor(source,"r");
                if(descriptor==null) throw new java.io.IOException("ISO kon niet worden geopend.");
                try(FileInputStream input=new ParcelFileDescriptor.AutoCloseInputStream(descriptor)) {
                    long[] previous={0};
                    EflcIsoInstaller.install(input.getChannel(),new File(root,"game"),(copied,total,file)->{
                        long now=System.nanoTime();if(now-previous[0]<500000000) return;previous[0]=now;
                        runOnUiThread(()->status.setText("Installeren: "+(total==0?0:copied*100/total)+"%\n"+file));
                    });
                }
                outcome="Installatie klaar. Tik op Start EFLC.";
            } catch(Exception error) {outcome="Installatie gestopt: "+error.getMessage();}
            final String message=outcome;
            runOnUiThread(()->{busy=false;getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);refresh();status.setText(message);});
        },"eflc-install").start();
    }
}
